"""Offline tests for the authenticated, SSRF-resistant image proxy."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import ipaddress
import logging
from pathlib import Path
from typing import Sequence

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.investigation import (
    get_image_proxy_service,
    require_image_proxy_investigator,
    router as investigation_router,
)
import app.services.image_proxy_service as image_proxy_module
from app.security.auth import AuthenticatedUser, get_current_user
from app.services.image_proxy_service import (
    ImageProxyError,
    ImageProxyService,
    address_is_public_unicast,
    hostname_is_allowed,
)


PUBLIC_IP = "93.184.216.34"
SECOND_PUBLIC_IP = "8.8.8.8"
SAFE_IMAGE_URL = "https://pbs.twimg.com/media/example.png?format=png"
PNG_BYTES = b"\x89PNG\r\n\x1a\nmock-image"


def _principal(*roles: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        username="case.analyst",
        roles=tuple(roles),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        csrf_token="c" * 43,
        session_id="s" * 32,
    )


def _app(
    *,
    service: ImageProxyService | None = None,
    principal: AuthenticatedUser | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(investigation_router)
    if service is not None:
        app.dependency_overrides[get_image_proxy_service] = lambda: service
    if principal is not None:
        app.dependency_overrides[get_current_user] = lambda: principal
    return app


def _service(
    handler: httpx.MockTransport,
    *,
    addresses: dict[str, Sequence[str]] | None = None,
    max_image_bytes: int = 1024,
    max_redirects: int = 3,
) -> tuple[ImageProxyService, list[tuple[str, int]]]:
    resolutions: list[tuple[str, int]] = []
    address_map = addresses or {"pbs.twimg.com": (PUBLIC_IP,)}

    async def resolver(hostname: str, port: int) -> Sequence[str]:
        resolutions.append((hostname, port))
        return address_map.get(hostname, (PUBLIC_IP,))

    return (
        ImageProxyService(
            resolver=resolver,
            transport=handler,
            max_image_bytes=max_image_bytes,
            max_redirects=max_redirects,
        ),
        resolutions,
    )


@pytest.mark.parametrize(
    ("hostname", "allowed"),
    [
        ("instagram.fna.fbcdn.net", True),
        ("scontent.cdninstagram.com", True),
        ("p16.tiktokcdn-us.com", True),
        ("pbs.twimg.com", True),
        ("abs.twimg.com", True),
        ("media.licdn.com", True),
        ("secure.gravatar.com", True),
        ("0.gravatar.com", True),
        ("images.gravatarusercontent.com", True),
        ("subdomain.media.licdn.com", False),
        ("avatars.githubusercontent.com", False),
        ("fbcdn.net.attacker.example", False),
        ("gravatar.com.attacker.example", False),
        ("evilfbcdn.net", False),
        ("instagram.com", False),
        ("example.com", False),
    ],
)
def test_allowlist_covers_only_documented_image_cdn_suffixes(
    hostname: str,
    allowed: bool,
) -> None:
    assert hostname_is_allowed(hostname) is allowed


def test_proxy_requires_authenticated_investigator() -> None:
    outbound_calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal outbound_calls
        outbound_calls += 1
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG_BYTES)

    service, _resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service)) as client:
        unauthenticated = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )
    assert unauthenticated.status_code == 401

    with TestClient(
        _app(service=service, principal=_principal("breach_pii_viewer"))
    ) as client:
        wrong_role = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )
    assert wrong_role.status_code == 403
    assert outbound_calls == 0


@pytest.mark.parametrize(
    "target",
    [
        "file:///etc/passwd",
        "ftp://pbs.twimg.com/image.png",
        "http://pbs.twimg.com/image.png",
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data",
        "https://user:secret@pbs.twimg.com/image.png",
        "https://pbs.twimg.com:8443/image.png",
        "https://pbs.twimg.com.attacker.example/image.png",
    ],
)
def test_ssrf_and_malformed_targets_are_rejected_without_outbound_call(target: str) -> None:
    outbound_calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal outbound_calls
        outbound_calls += 1
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG_BYTES)

    service, resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": target},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Image URL is not permitted"}
    assert target not in response.text
    assert "secret" not in response.text
    assert outbound_calls == 0
    assert resolutions == []


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.2",),
        ("169.254.1.1",),
        ("::1",),
        ("::ffff:127.0.0.1",),
        ("fe80::1",),
        ("224.0.0.1",),
        ("ff02::1",),
        ("fec0::1",),
        ("2002:7f00:1::",),
        ("64:ff9b::7f00:1",),
        (PUBLIC_IP, "127.0.0.1"),
        ("192.0.2.10",),
    ],
)
def test_non_global_dns_answers_fail_closed(addresses: Sequence[str]) -> None:
    outbound_calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal outbound_calls
        outbound_calls += 1
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG_BYTES)

    service, resolutions = _service(
        httpx.MockTransport(handler),
        addresses={"pbs.twimg.com": addresses},
    )
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Image URL is not permitted"}
    assert outbound_calls == 0
    assert resolutions == [("pbs.twimg.com", 443)]


@pytest.mark.parametrize(
    ("raw_address", "allowed"),
    [
        (PUBLIC_IP, True),
        ("224.0.0.1", False),
        ("ff02::1", False),
        ("fec0::1", False),
        ("2002:7f00:1::", False),
        ("64:ff9b::7f00:1", False),
    ],
)
def test_only_public_unicast_addresses_are_allowed(raw_address: str, allowed: bool) -> None:
    assert address_is_public_unicast(ipaddress.ip_address(raw_address)) is allowed


def test_redirect_target_is_revalidated_and_private_dns_is_rejected() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://media.licdn.com/private.png"},
        )

    service, resolutions = _service(
        httpx.MockTransport(handler),
        addresses={
            "pbs.twimg.com": (PUBLIC_IP,),
            "media.licdn.com": ("127.0.0.1",),
        },
    )
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 400
    assert "licdn" not in response.text
    assert len(requests) == 1
    assert resolutions == [("pbs.twimg.com", 443), ("media.licdn.com", 443)]


def test_safe_redirects_are_independently_resolved_and_ip_pinned() -> None:
    request_hosts: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        request_hosts.append((request.url.host, request.headers["host"]))
        if request.headers["host"] == "pbs.twimg.com":
            return httpx.Response(
                302,
                headers={"location": "https://media.licdn.com/final.png"},
            )
        return httpx.Response(200, headers={"content-type": "image/png"}, content=PNG_BYTES)

    service, resolutions = _service(
        httpx.MockTransport(handler),
        addresses={
            "pbs.twimg.com": (PUBLIC_IP,),
            "media.licdn.com": (SECOND_PUBLIC_IP,),
        },
    )
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert request_hosts == [
        (PUBLIC_IP, "pbs.twimg.com"),
        (SECOND_PUBLIC_IP, "media.licdn.com"),
    ]
    assert resolutions == [("pbs.twimg.com", 443), ("media.licdn.com", 443)]


@pytest.mark.parametrize(
    ("location", "expected_status"),
    [
        ("https://example.com/image.png", 400),
        ("http://127.0.0.1/image.png", 400),
        ("http://pbs.twimg.com/image.png", 400),
        (SAFE_IMAGE_URL, 502),
    ],
)
def test_unsafe_and_looping_redirects_are_rejected(
    location: str,
    expected_status: int,
) -> None:
    outbound_calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal outbound_calls
        outbound_calls += 1
        return httpx.Response(302, headers={"location": location})

    service, _resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == expected_status
    assert location not in response.text
    assert outbound_calls == 1


def test_relative_redirects_are_bounded_by_the_hard_cap() -> None:
    outbound_calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal outbound_calls
        outbound_calls += 1
        return httpx.Response(302, headers={"location": f"/hop-{outbound_calls}.png"})

    service, resolutions = _service(
        httpx.MockTransport(handler),
        max_redirects=1,
    )
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "Image could not be retrieved"}
    assert outbound_calls == 2
    assert resolutions == [("pbs.twimg.com", 443), ("pbs.twimg.com", 443)]


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Sequence[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


class _SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        await asyncio.sleep(0.05)
        yield PNG_BYTES


def test_oversized_chunked_response_is_stopped_while_streaming() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            stream=_ChunkStream((b"1234567890", b"abcdefghij")),
        )

    service, _resolutions = _service(
        httpx.MockTransport(handler),
        max_image_bytes=16,
    )
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "Image exceeds the proxy size limit"}
    assert SAFE_IMAGE_URL not in response.text


def test_oversized_declared_response_is_rejected_before_body_read() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-length": "17"},
            content=b"not-read",
        )

    service, _resolutions = _service(
        httpx.MockTransport(handler),
        max_image_bytes=16,
    )
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "Image exceeds the proxy size limit"}


def test_slow_drip_is_stopped_by_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            stream=_SlowStream(),
        )

    monkeypatch.setattr(image_proxy_module, "TOTAL_FETCH_TIMEOUT_SECONDS", 0.01)
    service, _resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "Image could not be retrieved"}


@pytest.mark.parametrize("content_type", ["text/html", "application/json", "image/svg+xml"])
def test_non_image_and_svg_responses_are_rejected(content_type: str) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": content_type},
            content=b"<content>not a safe raster image</content>",
        )

    service, _resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 415
    assert response.json() == {"detail": "Upstream response is not a supported image"}


def test_mime_and_file_signature_must_agree() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=b"GIF89a-mislabeled",
        )

    service, _resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 415
    assert response.json() == {"detail": "Upstream response is not a supported image"}


def test_encoded_upstream_response_is_rejected_without_decompression() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(
            200,
            headers={"content-type": "image/png", "content-encoding": "gzip"},
            stream=_ChunkStream((b"compressed-data",)),
        )

    service, _resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 415
    assert response.json() == {"detail": "Upstream response is not a supported image"}


def test_process_wide_concurrency_gate_fails_closed_when_busy() -> None:
    async def scenario() -> None:
        gate = asyncio.Semaphore(1)
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def resolver(_hostname: str, _port: int) -> Sequence[str]:
            return (PUBLIC_IP,)

        async def handler(_request: httpx.Request) -> httpx.Response:
            first_started.set()
            await release_first.wait()
            return httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=PNG_BYTES,
            )

        service = ImageProxyService(
            resolver=resolver,
            transport=httpx.MockTransport(handler),
            concurrency_gate=gate,
            concurrency_wait_timeout=0.01,
        )
        first = asyncio.create_task(service.fetch(SAFE_IMAGE_URL))
        await first_started.wait()
        try:
            with pytest.raises(ImageProxyError) as captured:
                await service.fetch(SAFE_IMAGE_URL)
            assert captured.value.code == "proxy_busy"
            assert captured.value.status_code == 503
        finally:
            release_first.set()
            await first

    asyncio.run(scenario())


def test_network_errors_do_not_leak_target_or_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "signed-cdn-secret"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"network failure {secret}", request=request)

    caplog.set_level(logging.WARNING)
    service, _resolutions = _service(httpx.MockTransport(handler))
    target = f"{SAFE_IMAGE_URL}&token={secret}"
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": target},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "Image could not be retrieved"}
    assert secret not in response.text
    assert secret not in caplog.text
    assert target not in caplog.text


def test_success_is_authenticated_get_without_csrf_and_returns_only_safe_headers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={
                "content-type": "image/png; charset=binary",
                "set-cookie": "upstream=must-not-pass",
                "x-upstream-secret": "must-not-pass",
            },
            content=PNG_BYTES,
        )

    service, resolutions = _service(httpx.MockTransport(handler))
    with TestClient(_app(service=service, principal=_principal("investigator"))) as client:
        response = client.get(
            "/api/v1/investigation/proxy_image",
            params={"url": SAFE_IMAGE_URL},
        )

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"].startswith("private")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in response.headers
    assert "x-upstream-secret" not in response.headers
    assert resolutions == [("pbs.twimg.com", 443)]
    assert len(requests) == 1
    assert requests[0].url.host == PUBLIC_IP
    assert requests[0].headers["host"] == "pbs.twimg.com"
    assert requests[0].extensions["sni_hostname"] == "pbs.twimg.com"
    assert "authorization" not in requests[0].headers
    assert "cookie" not in requests[0].headers


def test_frontend_loads_media_only_through_credentialed_proxy_urls() -> None:
    frontend_root = Path(__file__).resolve().parents[2] / "frontend" / "js"
    for script_name in ("app.js", "lea_pdf_exporter.js"):
        script = (frontend_root / script_name).read_text(encoding="utf-8")
        assert "/api/v1/investigation/proxy_image" in script
        assert 'crossorigin="use-credentials"' in script
    app_script = (frontend_root / "app.js").read_text(encoding="utf-8")
    exporter_script = (frontend_root / "lea_pdf_exporter.js").read_text(encoding="utf-8")
    assert '<img src="${item.url}"' not in app_script
    assert '<img src="${esc(item.url)}"' not in exporter_script
    assert "encodeURIComponent('${esc(item.url)}')" not in exporter_script
