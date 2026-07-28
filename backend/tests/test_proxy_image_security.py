import asyncio
import socket
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from fastapi import HTTPException

from backend.api.endpoints.investigation import proxy_image


class ProxyImageSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_and_non_http_targets_are_rejected_before_fetch(self) -> None:
        targets = (
            "http://127.0.0.1/admin",
            "http://[::1]/secret",
            "http://localhost/image.png",
            "http://user:password@example.com/image.png",
            "file:///etc/passwd",
        )

        for target in targets:
            with self.subTest(target=target), self.assertRaises(HTTPException) as raised:
                await proxy_image(target)
            self.assertEqual(raised.exception.status_code, 422)

    async def test_exact_youtube_thumbnail_hosts_are_allowed(self) -> None:
        original_async_client = httpx.AsyncClient

        def image_response(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=b"youtube-avatar",
                request=request,
            )

        def mock_async_client(*args, **kwargs) -> httpx.AsyncClient:
            kwargs["transport"] = httpx.MockTransport(image_response)
            return original_async_client(*args, **kwargs)

        loop = asyncio.get_running_loop()
        public_resolution = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            ),
        ]
        for hostname in ("yt3.googleusercontent.com", "yt3.ggpht.com"):
            with (
                self.subTest(hostname=hostname),
                patch.object(
                    loop,
                    "getaddrinfo",
                    new=AsyncMock(return_value=public_resolution),
                ),
                patch("httpx.AsyncClient", side_effect=mock_async_client),
            ):
                response = await proxy_image(f"https://{hostname}/avatar.jpg")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.media_type, "image/jpeg")
            self.assertEqual(response.body, b"youtube-avatar")

    async def test_youtube_thumbnail_host_near_matches_are_rejected(self) -> None:
        targets = (
            "https://evil.yt3.googleusercontent.com/avatar.jpg",
            "https://yt3.googleusercontent.com.attacker.example/avatar.jpg",
            "https://evil.yt3.ggpht.com/avatar.jpg",
            "https://yt3.ggpht.com.attacker.example/avatar.jpg",
        )

        for target in targets:
            with self.subTest(target=target), self.assertRaises(HTTPException) as raised:
                await proxy_image(target)
            self.assertEqual(raised.exception.status_code, 422)
            self.assertEqual(
                raised.exception.detail,
                "Image host is not an approved provider CDN",
            )

    async def test_allowed_youtube_host_resolving_private_is_rejected(self) -> None:
        loop = asyncio.get_running_loop()
        private_resolution = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            ),
        ]
        with (
            patch.object(
                loop,
                "getaddrinfo",
                new=AsyncMock(return_value=private_resolution),
            ),
            patch("httpx.AsyncClient") as async_client,
            self.assertRaises(HTTPException) as raised,
        ):
            await proxy_image("https://yt3.googleusercontent.com/avatar.jpg")

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail, "Private image targets are not allowed")
        async_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
