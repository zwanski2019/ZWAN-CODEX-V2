"""Interactsh OAST client for blind SSRF/XXE/injection confirmation."""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field

import httpx

from app.config import settings

_PUBLIC_SERVER = "https://oast.pro"


@dataclass
class Interaction:
    id: str
    protocol: str  # dns | http | smtp
    remote_address: str
    timestamp: str
    raw_request: str = ""
    raw_response: str = ""


class InteractshClient:
    """
    Registers a session with an Interactsh server and polls for interactions.
    Uses public oast.pro if INTERACTSH_SERVER is not set.
    """

    def __init__(self) -> None:
        self.server = (settings.interactsh_server or _PUBLIC_SERVER).rstrip("/")
        self.token = settings.interactsh_token
        self._session_id: str = ""
        self._secret: str = ""
        self._correlation_id: str = ""
        self._registered = False

    async def register(self) -> str:
        """Register a new session. Returns the OOB hostname to use in probes."""
        self._secret = os.urandom(32).hex()
        self._correlation_id = uuid.uuid4().hex[:20]
        self._session_id = uuid.uuid4().hex

        headers: dict = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = self.token

        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{self.server}/register",
                headers=headers,
                json={
                    "public-key": self._secret,
                    "secret-key": self._session_id,
                    "correlation-id": self._correlation_id,
                },
            )
            if r.is_success:
                self._registered = True
                domain = r.json().get("domain", "")
                return f"{self._correlation_id}.{domain}"

        # fallback — generate subdomain that will be polled
        return f"{self._correlation_id}.{self.server.replace('https://', '').replace('http://', '')}"

    def unique_host(self) -> str:
        """Generate a unique per-probe subdomain under the session."""
        probe_id = uuid.uuid4().hex[:8]
        base = self.server.replace("https://", "").replace("http://", "")
        return f"{probe_id}.{self._correlation_id}.{base}"

    async def poll(self, timeout_seconds: int = 30) -> list[Interaction]:
        """Poll for interactions received since registration."""
        if not self._registered:
            return []

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    headers: dict = {}
                    if self.token:
                        headers["Authorization"] = self.token
                    r = await client.get(
                        f"{self.server}/poll",
                        params={"id": self._correlation_id, "secret": self._session_id},
                        headers=headers,
                    )
                    if r.is_success:
                        data = r.json()
                        interactions = data.get("data", []) or []
                        if interactions:
                            return [
                                Interaction(
                                    id=i.get("unique-id", ""),
                                    protocol=i.get("protocol", ""),
                                    remote_address=i.get("remote-address", ""),
                                    timestamp=i.get("timestamp", ""),
                                    raw_request=i.get("raw-request", ""),
                                )
                                for i in interactions
                            ]
            except Exception:
                pass
            await asyncio.sleep(3)
        return []

    async def deregister(self) -> None:
        if not self._registered:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                headers: dict = {}
                if self.token:
                    headers["Authorization"] = self.token
                await client.post(
                    f"{self.server}/deregister",
                    headers=headers,
                    json={"correlation-id": self._correlation_id, "secret-key": self._session_id},
                )
        except Exception:
            pass


def new_client() -> InteractshClient:
    return InteractshClient()
