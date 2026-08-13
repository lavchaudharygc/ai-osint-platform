"""Small, typed Apify Actor runner used by social-platform integrations."""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

import httpx

import os

from app.config import settings


_ACTOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+[~/][A-Za-z0-9_.-]+$")
_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


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
    ) -> None:
        super().__init__(message)
        self.actor_id = actor_id
        self.code = code
        self.status_code = status_code
        self.run_id = run_id
        self.run_status = run_status

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "actor_id": self.actor_id,
            "status_code": self.status_code,
            "run_id": self.run_id,
            "run_status": self.run_status,
        }


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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        configured_token = settings.apify_api_token if token is None else token
        if not configured_token:
            configured_token = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN")
        self.token = configured_token.strip() if configured_token else None
        self.base_url = (base_url or getattr(settings, "apify_base_url", "https://api.apify.com/v2")).rstrip("/")
        self.http_timeout_seconds = http_timeout_seconds or getattr(settings, "apify_http_timeout_seconds", 30.0)
        self.run_timeout_seconds = run_timeout_seconds or getattr(settings, "apify_run_timeout_seconds", 300.0)
        self.poll_wait_seconds = poll_wait_seconds or getattr(settings, "apify_poll_wait_seconds", 5)
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.token)

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
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
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
                start_response = await client.post(
                    f"/acts/{rest_actor_id}/runs",
                    json=run_input,
                )
                start_payload = self._response_payload(
                    start_response,
                    actor_id=actor_id,
                    code="start_failed",
                )
                run_data = start_payload.get("data")
                if not isinstance(run_data, dict) or not run_data.get("id"):
                    raise ApifyClientError(
                        "Apify did not return an Actor run ID",
                        actor_id=actor_id,
                        code="invalid_run_response",
                        status_code=start_response.status_code,
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
                    )
                    polled_data = poll_payload.get("data")
                    if not isinstance(polled_data, dict):
                        raise ApifyClientError(
                            "Apify returned an invalid Actor run status payload",
                            actor_id=actor_id,
                            code="invalid_run_response",
                            status_code=poll_response.status_code,
                            run_id=run_id,
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
                    )

                dataset_id = run_data.get("defaultDatasetId")
                if not dataset_id:
                    raise ApifyClientError(
                        "Successful Actor run did not expose a default dataset",
                        actor_id=actor_id,
                        code="missing_dataset",
                        run_id=run_id,
                        run_status=run_status,
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
                )
                if not isinstance(items_payload, list):
                    raise ApifyClientError(
                        "Apify dataset response was not a list",
                        actor_id=actor_id,
                        code="invalid_dataset_response",
                        status_code=dataset_response.status_code,
                        run_id=run_id,
                        run_status=run_status,
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
                ) from exc
            except httpx.HTTPError as exc:
                raise ApifyClientError(
                    "Could not communicate with Apify",
                    actor_id=actor_id,
                    code="network_error",
                    run_id=run_id,
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
            ) from exc

        if response.is_error:
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise ApifyClientError(
                str(message or f"Apify returned HTTP {response.status_code}"),
                actor_id=actor_id,
                code=code,
                status_code=response.status_code,
                run_id=run_id,
            )
        if expect_object and not isinstance(payload, dict):
            raise ApifyClientError(
                "Apify returned an unexpected response shape",
                actor_id=actor_id,
                code="invalid_json_shape",
                status_code=response.status_code,
                run_id=run_id,
            )
        return payload

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if value is not None else None
