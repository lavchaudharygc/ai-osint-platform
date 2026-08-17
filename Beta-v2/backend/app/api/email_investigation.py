"""Authenticated, audited, single-target email-investigation endpoint."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.schemas.email_investigation import (
    EmailInvestigationRequest,
    EmailInvestigationResponse,
)
from app.services.email_investigation_service import EmailInvestigationService
from app.security.audit import AuditEvent, AuditReceipt, AuditUnavailable, get_audit_logger
from app.security.auth import AuthenticatedUser, require_csrf, require_roles


router = APIRouter(prefix="/api/v1/email-investigation", tags=["email-investigation"])
require_email_investigator = require_roles("investigator")


def get_email_investigation_service() -> EmailInvestigationService:
    """Construct a request-scoped service without exposing provider settings."""
    return EmailInvestigationService()


async def _record_restricted_access(
    *,
    user: AuthenticatedUser,
    request: EmailInvestigationRequest,
    outcome: str,
    field_labels: tuple[str, ...] = (),
) -> AuditReceipt:
    """Write the mandatory audit event or fail without disclosing records."""

    try:
        event = AuditEvent(
            analyst=user.username,
            action="breach.pii_view",
            outcome=outcome,
            case_id=request.case_id,
            reason_code=request.reason_code,
            target=str(request.email),
            field_labels=field_labels,
        )
        return await asyncio.to_thread(
            get_audit_logger().record,
            event,
        )
    except AuditUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Restricted disclosure audit is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc


@router.post("", response_model=EmailInvestigationResponse)
async def run_email_investigation(
    request: EmailInvestigationRequest,
    response: Response,
    user: AuthenticatedUser = Depends(require_email_investigator),
    _csrf_user: AuthenticatedUser = Depends(require_csrf),
    service: EmailInvestigationService = Depends(get_email_investigation_service),
) -> EmailInvestigationResponse:
    """Investigate one address; restricted disclosure requires RBAC and audit."""

    if request.include_restricted_breach_details and "breach_pii_viewer" not in user.roles:
        await _record_restricted_access(user=user, request=request, outcome="denied")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role permissions for restricted breach details",
            headers={"Cache-Control": "no-store"},
        )

    if request.include_restricted_breach_details:
        # Record the authorized access attempt before the provider can return
        # contact data. A second, field-aware record is durably appended before
        # any restricted values are disclosed to the browser.
        await _record_restricted_access(user=user, request=request, outcome="requested")

    result = await service.investigate(request)
    result.authorization.authenticated_user = user.username
    result.authorization.roles = list(user.roles)

    if not request.include_restricted_breach_details:
        # Enforce the disclosure boundary at the route as well as in the
        # collector. A future provider-adapter regression must not turn the
        # default metadata response into an unaudited contact-data response.
        result.breach_intelligence.restricted_details_included = False
        result.breach_intelligence.restricted_record_count = 0
        result.breach_intelligence.restricted_records_truncated = False
        for database in result.breach_intelligence.databases:
            database.restricted_records = []
            database.records_truncated = False
    else:
        field_labels = tuple(
            sorted(
                {
                    field.key
                    for database in result.breach_intelligence.databases
                    for record in database.restricted_records
                    for field in record.fields
                }
            )
        )
        audit_outcome = (
            "success"
            if field_labels
            else result.breach_intelligence.status
            if result.breach_intelligence.status in {"provider_error", "not_configured", "disabled"}
            else "no_records"
        )
        receipt = await _record_restricted_access(
            user=user,
            request=request,
            outcome=audit_outcome,
            field_labels=field_labels,
        )
        result.authorization.restricted_disclosure = "audited"
        result.authorization.audit_event_id = receipt.event_id

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return result
