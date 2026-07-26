import unittest

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


if __name__ == "__main__":
    unittest.main()
