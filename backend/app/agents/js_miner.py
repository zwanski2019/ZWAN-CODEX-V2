"""JSMinerAgent — JS bundle fetch, source map detection, LLM-driven extraction."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx as _httpx

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Asset, Secret
from app.tools import katana as katana_tool

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "js_miner.md"

_SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']([A-Za-z0-9_\-]{20,})', "api_key"),
    (r'(?i)(secret|token|password|passwd|pwd)\s*[:=]\s*["\']([A-Za-z0-9_\-\.]{8,})', "secret"),
    (r'sk-[A-Za-z0-9]{32,}', "openai_key"),
    (r'ghp_[A-Za-z0-9]{36}', "github_pat"),
    (r'AKIA[A-Z0-9]{16}', "aws_access_key"),
    (r'AIza[0-9A-Za-z\-_]{35}', "google_api_key"),
    (r'(?i)bearer\s+([A-Za-z0-9\-_\.]{20,})', "bearer_token"),
    (r'(?i)(client[_-]?secret)\s*[:=]\s*["\']([A-Za-z0-9_\-]{8,})', "oauth_client_secret"),
]

_ENDPOINT_PATTERN = re.compile(
    r'["\`](\s*/[a-z0-9_\-/]{2,}(?:\?[a-z0-9_=&%]{0,50})?)["\`]', re.IGNORECASE
)


def _extract_regex_secrets(js: str, source_url: str) -> list[dict]:
    found: list[dict] = []
    for pattern, kind in _SECRET_PATTERNS:
        for m in re.finditer(pattern, js):
            value = m.group(0)[:200]
            found.append({
                "type": kind,
                "value": value,
                "source_url": source_url,
                "context": js[max(0, m.start() - 50):m.end() + 50],
            })
    return found


def _extract_endpoints(js: str) -> list[str]:
    eps: set[str] = set()
    for m in _ENDPOINT_PATTERN.finditer(js):
        ep = m.group(1).strip()
        if len(ep) > 2 and not ep.startswith("//"):
            eps.add(ep)
    return list(eps)


@register_agent
class JsMinerAgent(BaseAgent):
    name = "js_miner"

    async def _execute(self) -> dict:
        system_prompt = _PROMPT_PATH.read_text()

        from sqlalchemy import select
        result = await self.db.execute(
            select(Asset).where(
                Asset.engagement_id == self.engagement.id,
                Asset.is_live == True,
            )
        )
        assets = list(result.scalars().all())

        if not assets:
            await self._emit("trace", {"message": "No live assets — run ReconAgent first"})
            return {"status": "skipped", "reason": "no assets"}

        await self._emit("trace", {"message": f"Mining JS from {len(assets)} assets"})

        all_js_urls: list[str] = []
        for asset in assets:
            base = asset.meta.get("url") or f"https://{asset.host}"
            try:
                js_urls = await self._discover_js(base)
                all_js_urls.extend(js_urls)
                await self._emit("trace", {"message": f"{asset.host}: {len(js_urls)} JS files"})
            except Exception as e:
                await self._emit("trace", {"message": f"{asset.host} crawl error: {e}"})

        all_js_urls = list(set(all_js_urls))[:50]
        await self._emit("trace", {"message": f"Processing {len(all_js_urls)} JS files"})

        all_endpoints: list[str] = []
        all_secrets: list[dict] = []
        llm_findings: list[dict] = []

        for js_url in all_js_urls:
            try:
                js_content = await self._fetch_js(js_url)
                if not js_content:
                    continue

                secrets = _extract_regex_secrets(js_content, js_url)
                endpoints = _extract_endpoints(js_content)
                all_endpoints.extend(endpoints)
                all_secrets.extend(secrets)

                if "sourceMappingURL=" in js_content:
                    await self._emit("trace", {"message": f"Source map: {js_url}"})

                if len(js_content) < 100_000 and (secrets or len(endpoints) > 5):
                    sample = js_content[:8000]
                    try:
                        llm_out, _ = await self.llm.complete(
                            model=settings.llm_light,
                            system=system_prompt,
                            messages=[{
                                "role": "user",
                                "content": f"Analyze JS from {js_url}:\n\n```js\n{sample}\n```\n\nReturn JSON only.",
                            }],
                            max_tokens=2000,
                        )
                        parsed = json.loads(llm_out.strip().strip("```json").strip("```"))
                        llm_findings.append({"url": js_url, "findings": parsed})
                    except Exception as e:
                        await self._emit("trace", {"message": f"LLM error {js_url}: {e}"})
            except Exception as e:
                await self._emit("trace", {"message": f"Error {js_url}: {e}"})

        # Persist secrets encrypted
        if settings.fernet_key:
            from cryptography.fernet import Fernet
            f = Fernet(settings.fernet_key.encode())
            for s in all_secrets:
                self.db.add(Secret(
                    id=str(uuid.uuid4()),
                    engagement_id=self.engagement.id,
                    source_url=s["source_url"],
                    secret_type=s["type"],
                    encrypted_value=f.encrypt(s["value"].encode()).decode(),
                    context=s.get("context", "")[:500],
                ))
            await self.db.commit()

        await self._emit("trace", {
            "message": f"Done: {len(all_endpoints)} endpoints, {len(all_secrets)} secrets",
        })

        return {
            "js_files": len(all_js_urls),
            "endpoints": list(set(all_endpoints))[:200],
            "secrets_count": len(all_secrets),
            "llm_findings": llm_findings,
        }

    async def _discover_js(self, base_url: str) -> list[str]:
        results = await katana_tool.crawl(base_url, depth=2, timeout=60)
        return katana_tool.filter_js_urls(results)

    async def _fetch_js(self, url: str) -> str:
        async with _httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            ct = r.headers.get("content-type", "")
            if r.is_success and ("javascript" in ct or url.endswith(".js")):
                return r.text
        return ""
