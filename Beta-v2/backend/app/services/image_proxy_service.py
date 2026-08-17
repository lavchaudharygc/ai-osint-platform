"""Bounded, SSRF-resistant image retrieval for authenticated UI rendering."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import socket
from typing import Awaitable, Callable, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


# Supported public image hosts emitted by the gallery's current collectors:
# - Meta/Instagram: *.fbcdn.net, *.cdninstagram.com
# - TikTok: *.tiktokcdn.com, *.tiktokcdn-us.com
# - X/Twitter: abs.twimg.com and pbs.twimg.com
# - LinkedIn: media.licdn.com
# - Gravatar: documented avatar hosts and *.gravatarusercontent.com
# Keep this list collector-specific. General web, platform, user-content, and
# unrelated image hosting domains are intentionally absent.
ALLOWED_IMAGE_HOSTNAMES = frozenset(
    {
        "abs.twimg.com",
        "0.gravatar.com",
        "1.gravatar.com",
        "2.gravatar.com",
        "gravatar.com",
        "media.licdn.com",
        "pbs.twimg.com",
        "secure.gravatar.com",
        "www.gravatar.com",
    }
)
ALLOWED_IMAGE_HOST_SUFFIXES = frozenset(
    {
        "cdninstagram.com",
        "fbcdn.net",
        "gravatarusercontent.com",
        "tiktokcdn-us.com",
        "tiktokcdn.com",
    }
)

SAFE_IMAGE_MEDIA_TYPES = frozenset(
    {
        "image/avif",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

_NAT64_WELL_KNOWN = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_LOCAL_USE = ipaddress.IPv6Network("64:ff9b:1::/48")

MAX_URL_CHARACTERS = 4096
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
DNS_TIMEOUT_SECONDS = 2.0
TOTAL_FETCH_TIMEOUT_SECONDS = 15.0
CONCURRENCY_WAIT_TIMEOUT_SECONDS = 1.0
_IMAGE_PROXY_CONCURRENCY_GATE = asyncio.Semaphore(4)

Resolver = Callable[[str, int], Awaitable[Sequence[str]]]


class ImageProxyError(RuntimeError):
    """An internal image-proxy failure with a safe response category."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ProxiedImage:
    """Validated image bytes safe to return to the authenticated browser."""

    content: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class _ValidatedTarget:
    canonical_url: str
    pinned_url: str
    hostname: str
    scheme: str


async def resolve_host_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve a hostname without blocking the event loop."""

    try:
        records = await asyncio.wait_for(
            asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            ),
            timeout=DNS_TIMEOUT_SECONDS,
        )
    except (OSError, TimeoutError) as exc:
        raise ImageProxyError("target_not_permitted", 400) from exc

    addresses: list[str] = []
    for record in records:
        try:
            address = str(record[4][0])
        except (IndexError, TypeError):
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ImageProxyError("target_not_permitted", 400)
    return tuple(addresses)


def hostname_is_allowed(hostname: str) -> bool:
    """Return whether a normalized hostname belongs to a supported image CDN."""

    return hostname in ALLOWED_IMAGE_HOSTNAMES or any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in ALLOWED_IMAGE_HOST_SUFFIXES
    )


def _normalized_media_type(raw_content_type: str) -> str | None:
    media_type = raw_content_type.partition(";")[0].strip().casefold()
    return media_type if media_type in SAFE_IMAGE_MEDIA_TYPES else None


def _content_matches_media_type(content: bytes, media_type: str) -> bool:
    """Confirm the response has the expected raster-image file signature."""

    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if media_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if media_type == "image/webp":
        return (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
    if media_type == "image/avif":
        return (
            len(content) >= 16
            and content[4:8] == b"ftyp"
            and any(brand in content[8:64] for brand in (b"avif", b"avis"))
        )
    return False


def address_is_public_unicast(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Reject non-unicast, reserved, and address-transition DNS results."""

    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if (
            address.is_site_local
            or address.ipv4_mapped is not None
            or address.sixtofour is not None
            or address.teredo is not None
            or address in _NAT64_WELL_KNOWN
            or address in _NAT64_LOCAL_USE
        ):
            return False
    return True


class ImageProxyService:
    """Fetch allowlisted images with DNS pinning, redirect, and size limits."""

    def __init__(
        self,
        *,
        resolver: Resolver = resolve_host_addresses,
        transport: httpx.AsyncBaseTransport | None = None,
        max_image_bytes: int = MAX_IMAGE_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        concurrency_gate: asyncio.Semaphore = _IMAGE_PROXY_CONCURRENCY_GATE,
        concurrency_wait_timeout: float = CONCURRENCY_WAIT_TIMEOUT_SECONDS,
    ) -> None:
        self._resolver = resolver
        self._transport = transport
        self._max_image_bytes = max(1, min(max_image_bytes, MAX_IMAGE_BYTES))
        self._max_redirects = max(0, min(max_redirects, MAX_REDIRECTS))
        self._concurrency_gate = concurrency_gate
        self._concurrency_wait_timeout = max(
            0.01,
            min(concurrency_wait_timeout, CONCURRENCY_WAIT_TIMEOUT_SECONDS),
        )

    async def fetch(self, raw_url: str) -> ProxiedImage:
        """Retrieve one image without exposing raw upstream data or errors."""

        acquired = False
        try:
            await asyncio.wait_for(
                self._concurrency_gate.acquire(),
                timeout=self._concurrency_wait_timeout,
            )
            acquired = True
        except TimeoutError as exc:
            raise ImageProxyError("proxy_busy", 503) from exc

        timeout = httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=1.0)
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=0)
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=timeout,
                limits=limits,
                transport=self._transport,
                trust_env=False,
                http2=False,
            ) as client:
                return await asyncio.wait_for(
                    self._fetch_with_client(client, raw_url),
                    timeout=TOTAL_FETCH_TIMEOUT_SECONDS,
                )
        except ImageProxyError:
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            raise ImageProxyError("upstream_unavailable", 502) from exc
        finally:
            if acquired:
                self._concurrency_gate.release()

    async def _fetch_with_client(
        self,
        client: httpx.AsyncClient,
        raw_url: str,
    ) -> ProxiedImage:
        current_url = raw_url
        visited: set[str] = set()

        for redirect_count in range(self._max_redirects + 1):
            target = await self._validate_and_pin(current_url)
            if target.canonical_url in visited:
                raise ImageProxyError("redirect_rejected", 502)
            visited.add(target.canonical_url)

            extensions = (
                {"sni_hostname": target.hostname}
                if target.scheme == "https"
                else None
            )
            headers = {
                "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif",
                "Accept-Encoding": "identity",
                "Host": target.hostname,
                "User-Agent": "Beta-v2-image-proxy/1.0",
            }
            async with client.stream(
                "GET",
                target.pinned_url,
                headers=headers,
                extensions=extensions,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    if redirect_count >= self._max_redirects:
                        raise ImageProxyError("redirect_rejected", 502)
                    location = response.headers.get("location", "")
                    if not location or len(location) > MAX_URL_CHARACTERS:
                        raise ImageProxyError("redirect_rejected", 502)
                    current_url = urljoin(target.canonical_url, location)
                    continue

                if response.status_code != 200:
                    raise ImageProxyError("upstream_unavailable", 502)

                media_type = _normalized_media_type(
                    response.headers.get("content-type", "")
                )
                if media_type is None:
                    raise ImageProxyError("unsupported_image", 415)
                content_encoding = response.headers.get("content-encoding", "").strip().casefold()
                if content_encoding not in {"", "identity"}:
                    raise ImageProxyError("unsupported_image", 415)

                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except ValueError as exc:
                        raise ImageProxyError("upstream_unavailable", 502) from exc
                    if declared_length < 0:
                        raise ImageProxyError("upstream_unavailable", 502)
                    if declared_length > self._max_image_bytes:
                        raise ImageProxyError("image_too_large", 413)

                body = bytearray()
                if response.is_stream_consumed:
                    # In-memory/mock transports may provide an already buffered
                    # response. The same strict cap still applies.
                    if len(response.content) > self._max_image_bytes:
                        raise ImageProxyError("image_too_large", 413)
                    body.extend(response.content)
                else:
                    async for chunk in response.aiter_raw():
                        if len(chunk) > self._max_image_bytes - len(body):
                            raise ImageProxyError("image_too_large", 413)
                        body.extend(chunk)
                if not body:
                    raise ImageProxyError("upstream_unavailable", 502)
                content = bytes(body)
                if not _content_matches_media_type(content, media_type):
                    raise ImageProxyError("unsupported_image", 415)
                return ProxiedImage(content=content, media_type=media_type)

        raise ImageProxyError("redirect_rejected", 502)

    async def _validate_and_pin(self, raw_url: str) -> _ValidatedTarget:
        if (
            not isinstance(raw_url, str)
            or not raw_url
            or len(raw_url) > MAX_URL_CHARACTERS
            or any(ord(character) <= 32 or ord(character) == 127 for character in raw_url)
        ):
            raise ImageProxyError("target_not_permitted", 400)

        try:
            parsed = urlsplit(raw_url)
            scheme = parsed.scheme.casefold()
            hostname_raw = parsed.hostname
            port = parsed.port
        except (TypeError, ValueError) as exc:
            raise ImageProxyError("target_not_permitted", 400) from exc

        if scheme != "https" or not hostname_raw:
            raise ImageProxyError("target_not_permitted", 400)
        if parsed.username is not None or parsed.password is not None:
            raise ImageProxyError("target_not_permitted", 400)
        if hostname_raw.endswith("."):
            raise ImageProxyError("target_not_permitted", 400)

        try:
            hostname = hostname_raw.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ImageProxyError("target_not_permitted", 400) from exc
        if not hostname or len(hostname) > 253:
            raise ImageProxyError("target_not_permitted", 400)

        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            # Image IP literals are never needed by the supported collectors.
            raise ImageProxyError("target_not_permitted", 400)

        if not hostname_is_allowed(hostname):
            raise ImageProxyError("target_not_permitted", 400)

        default_port = 443
        if port is not None and port != default_port:
            raise ImageProxyError("target_not_permitted", 400)
        resolved_port = port or default_port

        try:
            raw_addresses = await self._resolver(hostname, resolved_port)
        except ImageProxyError:
            raise
        except Exception as exc:
            raise ImageProxyError("target_not_permitted", 400) from exc
        if isinstance(raw_addresses, (str, bytes)) or not raw_addresses:
            raise ImageProxyError("target_not_permitted", 400)

        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for raw_address in raw_addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError as exc:
                raise ImageProxyError("target_not_permitted", 400) from exc
            if not address_is_public_unicast(address):
                raise ImageProxyError("target_not_permitted", 400)
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            raise ImageProxyError("target_not_permitted", 400)

        # Prefer IPv4 for compatibility, while still accepting pinned public IPv6.
        selected_address = sorted(
            addresses,
            key=lambda address: (address.version, str(address)),
        )[0]
        pinned_host = (
            f"[{selected_address.compressed}]"
            if selected_address.version == 6
            else selected_address.compressed
        )
        path = parsed.path or "/"
        canonical_url = urlunsplit((scheme, hostname, path, parsed.query, ""))
        pinned_url = urlunsplit((scheme, pinned_host, path, parsed.query, ""))
        return _ValidatedTarget(
            canonical_url=canonical_url,
            pinned_url=pinned_url,
            hostname=hostname,
            scheme=scheme,
        )
