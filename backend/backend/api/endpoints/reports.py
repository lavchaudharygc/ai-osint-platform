"""Report generation API endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from backend.api.endpoints.investigation import _INVESTIGATION_STORE
from backend.schemas.reports import ReportFormat, ReportGenerationResponse

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.post("/generate-report/{investigation_id}", response_model=ReportGenerationResponse)
async def generate_report(
    investigation_id: str,
    format: ReportFormat = Query(default="pdf"),
) -> ReportGenerationResponse:
    if investigation_id not in _INVESTIGATION_STORE:
        raise HTTPException(status_code=404, detail="Investigation not found")
    extension = "html" if format == "html" else "pdf"
    return ReportGenerationResponse(
        investigation_id=investigation_id,
        format=format,
        report_url=f"/reports/{investigation_id}.{extension}",
        generated_at=datetime.now(UTC),
    )
