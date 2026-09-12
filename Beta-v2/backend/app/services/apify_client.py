"""Small, typed Apify Actor runner used by social-platform integrations."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger(__name__)
_ACTOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+[~/][A-Za-z0-9_.-]+$")
_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
_AUTH_ERROR_TYPES = {
    "invalid-token",
    "invalid-token-type",
    "missing-api-token",
    "token-not-provided",
}
_ACCESS_ERROR_TYPES = {
    "full-permission-actor-blocked-for-admin",
    "full-permission-actor-not-approved",
    "insufficient-permissions",
    "missing-actor-rights",
    "unsupported-permission",
}
_BILLING_ERROR_TYPES = {
    "apify-plan-required-to-use-paid-actor",
    "failed-to-charge-user",
    "missing-billing-info",
    "no-payment-method-available",
    "not-enough-usage-to-run-paid-actor",
}
_QUOTA_ERROR_TYPES = {
    "limit-reached",
    "monthly-usage-limit-exceeded",
    "monthly-usage-limit-reached",
    "monthly-usage-limit-too-low",
}


class ApifyClientError(RuntimeError):
    """An Apify API or Actor-run failure with safe, serializable metadata."""

    def __init__(
        self,
        message: str,
        *,
        actor_id: str,
        code: str,
        status_code: int | None = None,
        run_id: str | None = None,
        run_status: str | None = None,
        provider_error_type: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.actor_id = actor_id
        self.code = code
        self.status_code = status_code
        self.run_id = run_id
        self.run_status = run_status
        self.provider_error_type = provider_error_type
        self.operation = operation

    @property
    def public_message(self) -> str:
        """Return an operator-safe explanation without echoing provider text."""
        messages = {
            "not_configured": "Apify API token is not configured",
            "invalid_token": "Apify rejected the configured API token",
            "access_denied": "Apify token or Actor permissions do not allow this run",
            "billing_required": "Apify billing, subscription, or spending permission is required",
            "quota_exhausted": "Apify monthly usage limit is exhausted",
            "rate_limited": "Apify rate limit was reached",
            "http_timeout": "Apify request timed out",
            "network_error": "Apify could not be reached",
            "run_timeout": "Apify Actor run exceeded the configured timeout",
            "actor_run_failed": "Apify Actor run failed",
        }
        return messages.get(self.code, "Apify provider request failed")

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.public_message,
            "actor_id": self.actor_id,
            "status_code": self.status_code,
            "run_id": self.run_id,
            "run_status": self.run_status,
            "provider_error_type": self.provider_error_type,
            "operation": self.operation,
        }


@dataclass(slots=True)
class ApifyAccountCapacity:
    """Privacy-safe snapshot of Apify account capacity."""

    state: str
    configured: bool
    checked: bool
    can_start_runs: bool | None
    monthly_usage_usd: float | None = None
    monthly_limit_usd: float | None = None
    remaining_usd: float | None = None
    usage_cycle_ends_at: str | None = None
    status_code: int | None = None
    provider_error_type: str | None = None
    checked_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ApifyActorRun:
    """Completed Actor run and the bounded items fetched from its default dataset."""

    actor_id: str
    run_id: str
    run_status: str
    dataset_id: str
    items: list[dict[str, Any]]
    started_at: str | None = None
    finished_at: str | None = None
    status_message: str | None = None
    fetched_at: str = ""

    def as_dict(self, *, include_items: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if not include_items:
            payload.pop("items", None)
        return payload


class ApifyActorClient:
    """Run an Actor, wait for a terminal state, and fetch its default dataset.

    Actor runs are started asynchronously instead of relying on the five-minute
    synchronous endpoint. This retains the run ID for provenance, permits a
    bounded application timeout, and lets us abort a run that outlives it.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        http_timeout_seconds: float | None = None,
        run_timeout_seconds: float | None = None,
        poll_wait_seconds: int | None = None,
        quota_check_ttl_seconds: int | None = None,
        quota_check_timeout_seconds: float | None = None,
        max_total_charge_usd_per_run: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_token = settings.apify_api_token if token is None else token
        self.token = configured_token.strip() if configured_token else None
        self.base_url = (base_url or getattr(settings, "apify_base_url", "https://api.apify.com/v2")).rstrip("/")
        self.http_timeout_seconds = http_timeout_seconds or getattr(settings, "apify_http_timeout_seconds", 30.0)
        self.run_timeout_seconds = run_timeout_seconds or getattr(settings, "apify_run_timeout_seconds", 300.0)
        self.poll_wait_seconds = poll_wait_seconds or getattr(settings, "apify_poll_wait_seconds", 5)
        self.quota_check_ttl_seconds = quota_check_ttl_seconds or getattr(
            settings,
            "apify_quota_check_ttl_seconds",
            300,
        )
        self.quota_check_timeout_seconds = (
            quota_check_timeout_seconds
            if quota_check_timeout_seconds is not None
            else getattr(settings, "apify_quota_check_timeout_seconds", 10.0)
        )
        self.max_total_charge_usd_per_run = (
            max_total_charge_usd_per_run
            if max_total_charge_usd_per_run is not None
            else getattr(settings, "apify_max_total_charge_usd_per_run", 1.0)
        )
        self.transport = transport
        self._capacity: ApifyAccountCapacity | None = None
        self._capacity_cached_at = 0.0
        self._capacity_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._blocking_failure: tuple[str, int | None, str | None] | None = None

    def is_configured(self) -> bool:
        return bool(self.token)

    async def check_account_capacity(self, *, force: bool = False) -> ApifyAccountCapacity:
        """Check account usage with a read-only request and cache the result.

        A scoped token may be allowed to run an Actor while being forbidden to
        read account limits. That state is reported as unknown and does not
        block a run. A known exhausted monthly limit does block paid launches.
        """
        if not self.is_configured():
            return ApifyAccountCapacity(
                state="not_configured",
                configured=False,
                checked=False,
                can_start_runs=False,
            )

        now = monotonic()
        if (
            not force
            and self._capacity is not None
            and now - self._capacity_cached_at < float(self.quota_check_ttl_seconds)
        ):
            return self._capacity

        async with self._capacity_lock:
            now = monotonic()
            if (
                not force
                and self._capacity is not None
                and now - self._capacity_cached_at < float(self.quota_check_ttl_seconds)
            ):
                return self._capacity

            headers = self._headers()
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    headers=headers,
                    timeout=float(self.quota_check_timeout_seconds),
                    transport=self.transport,
                ) as client:
                    response = await client.get("/users/me/limits")
                payload = self._response_payload(
                    response,
                    actor_id="apify/account",
                    code="quota_check_failed",
                    operation="quota_check",
                )
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, dict):
                    raise ApifyClientError(
                        "Apify returned an invalid account-limits payload",
                        actor_id="apify/account",
                        code="invalid_quota_response",
                        status_code=response.status_code,
                        operation="quota_check",
                    )

                limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
                current = data.get("current") if isinstance(data.get("current"), dict) else {}
                cycle = (
                    data.get("monthlyUsageCycle")
                    if isinstance(data.get("monthlyUsageCycle"), dict)
                    else {}
                )
                used = self._optional_number(current.get("monthlyUsageUsd"))
                maximum = self._optional_number(limits.get("maxMonthlyUsageUsd"))
                exhausted = bool(
                    used is not None
                    and maximum is not None
                    and maximum >= 0
                    and used >= maximum
                )
                remaining = (
                    max(0.0, round(maximum - used, 4))
                    if used is not None and maximum is not None
                    else None
                )
                capacity = ApifyAccountCapacity(
                    state="quota_exhausted" if exhausted else "ready",
                    configured=True,
                    checked=True,
                    can_start_runs=not exhausted,
                    monthly_usage_usd=round(used, 4) if used is not None else None,
                    monthly_limit_usd=round(maximum, 4) if maximum is not None else None,
                    remaining_usd=remaining,
                    usage_cycle_ends_at=self._optional_string(cycle.get("endAt")),
                    status_code=response.status_code,
                    checked_at=datetime.now(UTC).isoformat(),
                )
            except ApifyClientError as exc:
                # A 403 here can mean a correctly scoped run-only token. Do not
                # mistake an unavailable quota view for proof runs are denied.
                can_start = False if exc.code == "invalid_token" else None
                capacity = ApifyAccountCapacity(
                    state=(
                        "invalid_token"
                        if exc.code == "invalid_token"
                        else "quota_check_unavailable"
                    ),
                    configured=True,
                    checked=True,
                    can_start_runs=can_start,
                    status_code=exc.status_code,
                    provider_error_type=exc.provider_error_type,
                    checked_at=datetime.now(UTC).isoformat(),
                )
            except Exception as exc:
                capacity = ApifyAccountCapacity(
                    state="quota_check_unavailable",
                    configured=True,
                    checked=True,
                    can_start_runs=None,
                    checked_at=datetime.now(UTC).isoformat(),
                )
                logger.warning(
                    "event=apify_capacity_check_failed error_type=%s",
                    type(exc).__name__,
                )

            self._capacity = capacity
            self._capacity_cached_at = monotonic()
            logger.info(
                "event=apify_capacity_checked state=%s can_start_runs=%s",
                capacity.state,
                capacity.can_start_runs,
            )
            return capacity

    def capacity_snapshot(self) -> ApifyAccountCapacity | None:
        """Return the last safe capacity snapshot without network access."""
        return self._capacity

    @staticmethod
    def rest_actor_id(actor_id: str) -> str:
        """Validate a Store actor ID and convert ``owner/name`` to REST form."""
        candidate = actor_id.strip()
        if not _ACTOR_ID_PATTERN.fullmatch(candidate):
            raise ValueError("Actor ID must use the form 'owner/name'")
        owner, name = re.split(r"[~/]", candidate, maxsplit=1)
        return f"{owner}~{name}"

    async def run_actor(
        self,
        actor_id: str,
        run_input: dict[str, Any],
        *,
        dataset_limit: int,
    ) -> ApifyActorRun:
        """Execute one Actor and return at most ``dataset_limit`` clean items."""
        if not self.is_configured():
            raise ApifyClientError(
                "APIFY_API_TOKEN is not configured",
                actor_id=actor_id,
                code="not_configured",
            )
        if not isinstance(run_input, dict):
            raise TypeError("run_input must be a dictionary")
        if not 1 <= dataset_limit <= 10_000:
            raise ValueError("dataset_limit must be between 1 and 10000")
        rest_actor_id = self.rest_actor_id(actor_id)

        capacity = await self.check_account_capacity()
        if capacity.state == "quota_exhausted":
            raise ApifyClientError(
                "Apify monthly usage is at or above the configured account limit",
                actor_id=actor_id,
                code="quota_exhausted",
                operation="quota_check",
            )
        if capacity.state == "invalid_token":
            raise ApifyClientError(
                "Apify rejected the configured token during the account check",
                actor_id=actor_id,
                code="invalid_token",
                status_code=capacity.status_code,
                provider_error_type=capacity.provider_error_type,
                operation="quota_check",
            )

        if self._blocking_failure is not None:
            blocked_code, blocked_status, blocked_provider_type = self._blocking_failure
            raise ApifyClientError(
                "A previous Apify launch was denied during this investigation",
                actor_id=actor_id,
                code=blocked_code,
                status_code=blocked_status,
                provider_error_type=blocked_provider_type,
                operation="start",
            )

        headers = self._headers()
        request_timeout = max(
            float(self.http_timeout_seconds),
            float(self.poll_wait_seconds) + 10.0,
        )
        run_id: str | None = None
        run_is_terminal = False

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=request_timeout,
            transport=self.transport,
        ) as client:
            try:
                # Serialize only the launch handshake. Once one launch succeeds,
                # the paid Actors can run concurrently. If a launch is denied,
                # later launches in this investigation are stopped immediately.
                async with self._start_lock:
                    if self._blocking_failure is not None:
                        blocked_code, blocked_status, blocked_provider_type = self._blocking_failure
                        raise ApifyClientError(
                            "A previous Apify launch was denied during this investigation",
                            actor_id=actor_id,
                            code=blocked_code,
                            status_code=blocked_status,
                            provider_error_type=blocked_provider_type,
                            operation="start",
                        )
                    start_response = await client.post(
                        f"/actors/{rest_actor_id}/runs",
                        params={
                            "maxTotalChargeUsd": self.max_total_charge_usd_per_run,
                        },
                        json=run_input,
                    )
                    try:
                        start_payload = self._response_payload(
                            start_response,
                            actor_id=actor_id,
                            code="start_failed",
                            operation="start",
                        )
                    except ApifyClientError as exc:
                        if exc.code in {
                            "access_denied",
                            "billing_required",
                            "invalid_token",
                            "quota_exhausted",
                        }:
                            self._blocking_failure = (
                                exc.code,
                                exc.status_code,
                                exc.provider_error_type,
                            )
                        raise
                run_data = start_payload.get("data")
                if not isinstance(run_data, dict) or not run_data.get("id"):
                    raise ApifyClientError(
                        "Apify did not return an Actor run ID",
                        actor_id=actor_id,
                        code="invalid_run_response",
                        status_code=start_response.status_code,
                        operation="start",
                    )

                run_id = str(run_data["id"])
                deadline = monotonic() + float(self.run_timeout_seconds)
                while str(run_data.get("status", "")).upper() not in _TERMINAL_STATUSES:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise ApifyClientError(
                            f"Actor run exceeded {self.run_timeout_seconds:g} seconds",
                            actor_id=actor_id,
                            code="run_timeout",
                            run_id=run_id,
                            run_status=str(run_data.get("status") or "RUNNING"),
                            operation="poll",
                        )

                    wait_for_finish = max(
                        1,
                        min(60, int(self.poll_wait_seconds), int(max(1.0, remaining))),
                    )
                    poll_response = await client.get(
                        f"/actor-runs/{run_id}",
                        params={"waitForFinish": wait_for_finish},
                    )
                    poll_payload = self._response_payload(
                        poll_response,
                        actor_id=actor_id,
                        code="poll_failed",
                        run_id=run_id,
                        operation="poll",
                    )
                    polled_data = poll_payload.get("data")
                    if not isinstance(polled_data, dict):
                        raise ApifyClientError(
                            "Apify returned an invalid Actor run status payload",
                            actor_id=actor_id,
                            code="invalid_run_response",
                            status_code=poll_response.status_code,
                            run_id=run_id,
                            operation="poll",
                        )
                    run_data = polled_data

                run_status = str(run_data.get("status", "UNKNOWN")).upper()
                run_is_terminal = True
                if run_status != "SUCCEEDED":
                    message = str(run_data.get("statusMessage") or f"Actor run ended with {run_status}")
                    raise ApifyClientError(
                        message,
                        actor_id=actor_id,
                        code="actor_run_failed",
                        run_id=run_id,
                        run_status=run_status,
                        operation="run",
                    )

                dataset_id = run_data.get("defaultDatasetId")
                if not dataset_id:
                    raise ApifyClientError(
                        "Successful Actor run did not expose a default dataset",
                        actor_id=actor_id,
                        code="missing_dataset",
                        run_id=run_id,
                        run_status=run_status,
                        operation="dataset",
                    )

                dataset_response = await client.get(
                    f"/datasets/{dataset_id}/items",
                    params={
                        "format": "json",
                        "clean": "true",
                        "limit": dataset_limit,
                    },
                )
                items_payload = self._response_payload(
                    dataset_response,
                    actor_id=actor_id,
                    code="dataset_fetch_failed",
                    run_id=run_id,
                    expect_object=False,
                    operation="dataset",
                )
                if not isinstance(items_payload, list):
                    raise ApifyClientError(
                        "Apify dataset response was not a list",
                        actor_id=actor_id,
                        code="invalid_dataset_response",
                        status_code=dataset_response.status_code,
                        run_id=run_id,
                        run_status=run_status,
                        operation="dataset",
                    )
                items = [item for item in items_payload if isinstance(item, dict)]
                return ApifyActorRun(
                    actor_id=actor_id,
                    run_id=run_id,
                    run_status=run_status,
                    dataset_id=str(dataset_id),
                    items=items,
                    started_at=self._optional_string(run_data.get("startedAt")),
                    finished_at=self._optional_string(run_data.get("finishedAt")),
                    status_message=self._optional_string(run_data.get("statusMessage")),
                    fetched_at=datetime.now(UTC).isoformat(),
                )
            except asyncio.CancelledError:
                if run_id:
                    await self._abort_run(client, run_id)
                raise
            except ApifyClientError:
                if run_id and not run_is_terminal:
                    await self._abort_run(client, run_id)
                raise
            except httpx.TimeoutException as exc:
                if run_id:
                    await self._abort_run(client, run_id)
                raise ApifyClientError(
                    "Timed out while communicating with Apify",
                    actor_id=actor_id,
                    code="http_timeout",
                    run_id=run_id,
                    operation="request",
                ) from exc
            except httpx.HTTPError as exc:
                raise ApifyClientError(
                    "Could not communicate with Apify",
                    actor_id=actor_id,
                    code="network_error",
                    run_id=run_id,
                    operation="request",
                ) from exc

    async def _abort_run(self, client: httpx.AsyncClient, run_id: str) -> None:
        """Best-effort cleanup so an application timeout does not leave a paid run alive."""
        try:
            await client.post(f"/actor-runs/{run_id}/abort")
        except httpx.HTTPError:
            return

    @staticmethod
    def _response_payload(
        response: httpx.Response,
        *,
        actor_id: str,
        code: str,
        run_id: str | None = None,
        expect_object: bool = True,
        operation: str | None = None,
    ) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApifyClientError(
                "Apify returned a non-JSON response",
                actor_id=actor_id,
                code="invalid_json",
                status_code=response.status_code,
                run_id=run_id,
                operation=operation,
            ) from exc

        if response.is_error:
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            provider_error_type = (
                str(error.get("type"))
                if isinstance(error, dict) and error.get("type")
                else None
            )
            raise ApifyClientError(
                str(message or f"Apify returned HTTP {response.status_code}"),
                actor_id=actor_id,
                code=ApifyActorClient._classify_error(
                    provider_error_type,
                    response.status_code,
                    fallback=code,
                ),
                status_code=response.status_code,
                run_id=run_id,
                provider_error_type=provider_error_type,
                operation=operation,
            )
        if expect_object and not isinstance(payload, dict):
            raise ApifyClientError(
                "Apify returned an unexpected response shape",
                actor_id=actor_id,
                code="invalid_json_shape",
                status_code=response.status_code,
                run_id=run_id,
                operation=operation,
            )
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _classify_error(
        provider_error_type: str | None,
        status_code: int,
        *,
        fallback: str,
    ) -> str:
        normalized = (provider_error_type or "").strip().casefold()
        if normalized in _AUTH_ERROR_TYPES or status_code == 401:
            return "invalid_token"
        if normalized in _ACCESS_ERROR_TYPES:
            return "access_denied"
        if normalized in _QUOTA_ERROR_TYPES:
            return "quota_exhausted"
        if normalized in _BILLING_ERROR_TYPES or status_code == 402:
            return "billing_required"
        if normalized in {"rate-limit-exceeded", "too-many-requests"} or status_code == 429:
            return "rate_limited"
        if status_code == 403:
            return "access_denied"
        return fallback

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None
