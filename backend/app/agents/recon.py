"""ReconAgent — subdomain enum, live host probe, tech fingerprinting."""
from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Asset
from app.tools import httpx as httpx_tool
from app.tools import subfinder as subfinder_tool
from app.tools import katana as katana_tool


def _extract_root_domains(scope_urls: list[str]) -> list[str]:
    roots: set[str] = set()
    for url in scope_urls:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.hostname or ""
        # strip to root domain (last two parts)
        parts = host.split(".")
        if len(parts) >= 2:
            roots.add(".".join(parts[-2:]))
    return list(roots)


def _is_interesting(host: str) -> bool:
    keywords = ["api", "admin", "internal", "dev", "staging", "auth", "oauth",
                 "sso", "login", "portal", "manage", "dashboard", "backend",
                 "test", "uat", "sandbox", "beta", "legacy", "old", "v1", "v2"]
    return any(kw in host.lower() for kw in keywords)


@register_agent
class ReconAgent(BaseAgent):
    name = "recon"

    async def _execute(self) -> dict:
        scope_urls: list[str] = self.engagement.scope_urls
        await self._emit("trace", {"message": f"Starting recon on {len(scope_urls)} scope URLs"})

        # 1. Extract root domains
        roots = _extract_root_domains(scope_urls)
        await self._emit("trace", {"message": f"Root domains: {roots}"})

        # 2. Subfinder enumeration
        all_subs: list[str] = list(scope_urls)  # always include scope URLs themselves
        for root in roots:
            await self._emit("trace", {"message": f"Enumerating subdomains for {root}"})
            subs = await subfinder_tool.enumerate_subdomains(root)
            await self._emit("trace", {"message": f"{root}: {len(subs)} subdomains found"})
            all_subs.extend(subs)

        all_subs = list(set(all_subs))
        await self._emit("trace", {"message": f"Total unique hosts: {len(all_subs)}"})

        # 3. crt.sh passive enum for additional coverage
        for root in roots:
            try:
                crt_subs = await self._crt_sh(root)
                await self._emit("trace", {"message": f"crt.sh: {len(crt_subs)} additional for {root}"})
                all_subs.extend(crt_subs)
            except Exception as e:
                await self._emit("trace", {"message": f"crt.sh failed for {root}: {e}"})

        all_subs = list(set(all_subs))

        # 4. httpx live probe
        await self._emit("trace", {"message": f"Probing {len(all_subs)} hosts with httpx"})
        live_hosts = await httpx_tool.probe(all_subs)
        await self._emit("trace", {"message": f"Live hosts: {len(live_hosts)}"})

        # 5. Persist assets to DB
        assets_out: list[dict] = []
        for h in live_hosts:
            asset = Asset(
                id=str(uuid.uuid4()),
                engagement_id=self.engagement.id,
                host=h.host,
                ip=h.ip,
                tech_stack=h.tech,
                status_code=h.status_code,
                title=h.title,
                is_live=True,
                meta={
                    "server": h.server,
                    "cdn": h.cdn,
                    "url": h.url,
                    "interesting": _is_interesting(h.host),
                },
            )
            self.db.add(asset)
            assets_out.append({
                "host": h.host,
                "url": h.url,
                "status": h.status_code,
                "tech": h.tech,
                "interesting": _is_interesting(h.host),
            })

        await self.db.commit()

        interesting = [a for a in assets_out if a["interesting"]]
        await self._emit("trace", {
            "message": f"Recon complete. {len(live_hosts)} live, {len(interesting)} interesting",
            "interesting": interesting,
        })

        return {
            "total_discovered": len(all_subs),
            "live_count": len(live_hosts),
            "interesting_count": len(interesting),
            "assets": assets_out,
        }

    async def _crt_sh(self, domain: str) -> list[str]:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://crt.sh/?q=%.{domain}&output=json",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if not r.is_success:
                return []
            data = r.json()
            subs: set[str] = set()
            for entry in data:
                name = entry.get("name_value", "")
                for line in name.splitlines():
                    line = line.strip().lstrip("*.")
                    if domain in line and line:
                        subs.add(line)
            return list(subs)
