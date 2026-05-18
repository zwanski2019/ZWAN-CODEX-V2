"""Burp Pro REST API client. Optional — only active when BURP_API_KEY is set."""
from __future__ import annotations

import httpx

from app.config import settings


class BurpClient:
    def __init__(self) -> None:
        self.base = settings.burp_api_url.rstrip("/")
        self.key = settings.burp_api_key
        self._headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    async def send_request(self, request_raw: str, host: str, port: int = 443, https: bool = True) -> dict:
        """Send a raw HTTP request via Burp Repeater and return the response."""
        if not self.enabled:
            raise RuntimeError("Burp API key not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base}/burp/scanner/scans/named",
                headers=self._headers,
                json={
                    "urls": [f"{'https' if https else 'http'}://{host}:{port}"],
                    "rawRequest": request_raw,
                },
            )
            r.raise_for_status()
            return r.json()

    async def get_sitemap(self, prefix: str = "") -> list[dict]:
        """Fetch URLs from Burp's sitemap."""
        if not self.enabled:
            return []
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base}/burp/target/sitemap",
                headers=self._headers,
                params={"urlPrefix": prefix} if prefix else {},
            )
            r.raise_for_status()
            return r.json()

    async def send_to_repeater(self, host: str, port: int, https: bool, request: str) -> bool:
        """Add a request to Burp Repeater."""
        if not self.enabled:
            return False
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{self.base}/burp/repeater",
                headers=self._headers,
                json={"host": host, "port": port, "https": https, "request": request},
            )
            return r.is_success


burp = BurpClient()
