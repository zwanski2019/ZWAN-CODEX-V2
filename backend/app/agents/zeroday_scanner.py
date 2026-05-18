"""ZeroDayScannerAgent — AI-driven zero-day discovery in JS, APIs, and endpoints.

All HTTP requests carry X-JURA-BUGBOUNTY: Zwanski.
Only persists findings with CVSS >= 7.0 that pass the de-dup guard.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx as _httpx
from sqlalchemy import select

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Asset, Finding, FindingStatus, Severity

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "zeroday_scanner.md"

# Custom header on every outbound request
_BOUNTY_HEADERS: dict[str, str] = {
    "X-JURA-BUGBOUNTY": "Zwanski",
    "User-Agent": "Mozilla/5.0 (compatible; ZwanCodex-ZeroDayScanner/2.0)",
    "Accept": "text/html,application/json,*/*;q=0.9",
}

# Patterns that flag a JS file for deep LLM analysis
_INTERESTING_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r'\beval\s*\(',
    r'\bFunction\s*\(',
    r'__proto__\s*\[',
    r'Object\.prototype\s*\[',
    r'\.constructor\s*\[',
    r'prototype\s*\[',
    r'\bwindow\s*\[',
    r'document\.write\s*\(',
    r'innerHTML\s*=',
    r'dangerouslySetInnerHTML',
    r'postMessage\s*\(',
    r"addEventListener\s*\(\s*['\"]message['\"]",
    r'JSON\.parse\s*\([^;]{0,100}(?:location|search|hash|cookie)',
    r'sourceMappingURL=',
    r'\batob\s*\(',
    r'Math\.random\s*\(\)',
    r'localStorage\.(get|set)Item',
    r'sessionStorage\.(get|set)Item',
    r'\bfetch\s*\(\s*[^)]*\+',
    r'require\s*\(\s*(?:window|document|location|\$)',
    r'graphql|__typename|__schema',
    r'alg\s*:\s*["\'](?:none|HS256|RS256)',
    r'\.env\b|config\b.*secret|api_key|apiKey',
    r'role\s*:\s*["\']admin',
    r'is_admin\s*:\s*true',
    r'/admin|/internal|/debug|/actuator|/api/v[0-9]/admin',
    r'credits?\s*[:=]\s*[0-9]',
]]

# Titles that are definitely dupes / low-value — skip even if LLM flags them
_DUPE_TITLE_FRAGMENTS: list[str] = [
    "missing security header", "x-frame-options", "content-security-policy",
    "x-content-type", "hsts", "cors misconfiguration", "clickjacking",
    "rate limit", "ssl certificate", "tls version", "username enumeration",
    "self-xss", "password complexity", "information disclosure via server header",
]

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
}


def _is_minified(js: str) -> bool:
    if not js:
        return False
    lines = js.split("\n")
    avg_len = sum(len(l) for l in lines[:10]) / max(len(lines[:10]), 1)
    return avg_len > 300


def _rough_beautify(js: str) -> str:
    """Add newlines after ; { } to help the LLM parse minified code."""
    if not _is_minified(js):
        return js
    result = re.sub(r'([;{}])\s*', r'\1\n', js)
    return result


def _is_interesting(js: str) -> bool:
    return any(p.search(js) for p in _INTERESTING_PATTERNS)


def _is_dupe_title(title: str) -> bool:
    t = title.lower()
    return any(frag in t for frag in _DUPE_TITLE_FRAGMENTS)


@register_agent
class ZeroDayScannerAgent(BaseAgent):
    name = "zeroday_scanner"

    async def _execute(self) -> dict:
        system_prompt = _PROMPT_PATH.read_text()

        # 1. Collect live assets
        result = await self.db.execute(
            select(Asset).where(
                Asset.engagement_id == self.engagement.id,
                Asset.is_live == True,
            )
        )
        assets = list(result.scalars().all())

        scope_urls: list[str] = list(self.engagement.scope_urls)
        base_urls: list[str] = []

        for asset in assets:
            url = asset.meta.get("url") or f"https://{asset.host}"
            base_urls.append(url)

        # Fall back to raw scope_urls if no assets yet
        if not base_urls:
            base_urls = scope_urls

        if not base_urls:
            await self._emit("trace", {"message": "No targets — add scope URLs to engagement"})
            return {"status": "skipped", "reason": "no targets"}

        await self._emit("trace", {
            "message": f"Zero-Day scan starting on {len(base_urls)} targets"
        })

        # 2. Collect JS files
        all_js_urls: list[str] = []
        all_endpoints: list[str] = []

        for base in base_urls:
            try:
                js_urls, endpoints = await self._crawl_target(base)
                all_js_urls.extend(js_urls)
                all_endpoints.extend(endpoints)
                await self._emit("trace", {
                    "message": f"{base}: {len(js_urls)} JS files, {len(endpoints)} endpoints"
                })
            except Exception as e:
                await self._emit("trace", {"message": f"Crawl error {base}: {e}"})

        all_js_urls = list(dict.fromkeys(all_js_urls))[:60]
        all_endpoints = list(dict.fromkeys(all_endpoints))[:100]

        await self._emit("trace", {
            "message": f"Analyzing {len(all_js_urls)} JS files + {len(all_endpoints)} endpoints"
        })

        # 3. Deep-analyze JS files
        raw_findings: list[dict] = []

        for js_url in all_js_urls:
            try:
                js_content = await self._fetch(js_url)
                if not js_content or len(js_content) < 200:
                    continue

                if not _is_interesting(js_content):
                    continue

                beautified = _rough_beautify(js_content)
                sample = beautified[:15_000]

                await self._emit("trace", {"message": f"LLM analysis: {js_url}"})

                llm_out, _ = await self.llm.complete(
                    model=settings.llm_heavy,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Target JS file: {js_url}\n\n"
                            f"```javascript\n{sample}\n```\n\n"
                            "Analyze for zero-day and advanced logic vulnerabilities. "
                            "Return JSON array only."
                        ),
                    }],
                    max_tokens=4000,
                    temperature=0.1,
                )

                findings = self._parse_llm_output(llm_out)
                for f in findings:
                    f["_source"] = js_url
                raw_findings.extend(findings)

            except Exception as e:
                await self._emit("trace", {"message": f"JS analysis error {js_url}: {e}"})

        # 4. Endpoint logic analysis (batch interesting endpoints)
        if all_endpoints:
            endpoint_batch = all_endpoints[:30]
            endpoint_responses = await self._probe_endpoints(endpoint_batch)

            if endpoint_responses:
                try:
                    ep_summary = json.dumps(endpoint_responses[:20], indent=2)[:12_000]
                    llm_out, _ = await self.llm.complete(
                        model=settings.llm_heavy,
                        system=system_prompt,
                        messages=[{
                            "role": "user",
                            "content": (
                                f"API endpoint probe results for {self.engagement.scope_urls}:\n\n"
                                f"```json\n{ep_summary}\n```\n\n"
                                "Identify zero-day logic flaws, broken authorization, "
                                "mass assignment, or race condition indicators. "
                                "Return JSON array only."
                            ),
                        }],
                        max_tokens=4000,
                        temperature=0.1,
                    )
                    ep_findings = self._parse_llm_output(llm_out)
                    for f in ep_findings:
                        f["_source"] = "endpoint_probe"
                    raw_findings.extend(ep_findings)
                except Exception as e:
                    await self._emit("trace", {"message": f"Endpoint analysis error: {e}"})

        # 5. Filter and persist
        persisted = 0
        killed = 0

        # Load existing finding titles to avoid exact dupes
        existing_result = await self.db.execute(
            select(Finding.title).where(Finding.engagement_id == self.engagement.id)
        )
        existing_titles = {row[0].lower() for row in existing_result.all()}

        for raw in raw_findings:
            title = raw.get("title", "").strip()
            if not title:
                continue

            # De-dup guard
            if _is_dupe_title(title):
                killed += 1
                continue

            if title.lower() in existing_titles:
                killed += 1
                continue

            cvss = float(raw.get("cvss_estimate", 0))
            if cvss < 7.0:
                killed += 1
                continue

            sev_str = raw.get("severity", "high").lower()
            if sev_str not in _SEVERITY_MAP:
                sev_str = "high"

            finding = Finding(
                id=str(uuid.uuid4()),
                engagement_id=self.engagement.id,
                title=title,
                severity=_SEVERITY_MAP[sev_str],
                status=FindingStatus.PENDING,
                cvss_score=cvss,
                description=raw.get("description", ""),
                reproducer=raw.get("poc", ""),
                impact=raw.get("exploit_chain", ""),
                http_transcript=raw.get("_source", ""),
                meta={
                    "source_agent": "zeroday_scanner",
                    "category": raw.get("category", "logic_flaw"),
                    "location": raw.get("location", ""),
                },
            )
            self.db.add(finding)
            existing_titles.add(title.lower())
            persisted += 1
            await self._emit("finding", {"title": title, "severity": sev_str, "cvss": cvss})

        await self.db.commit()

        await self._emit("trace", {
            "message": (
                f"Zero-Day scan complete: {persisted} findings persisted, "
                f"{killed} killed (dupe/low-severity)"
            )
        })

        return {
            "js_files_analyzed": len(all_js_urls),
            "endpoints_probed": len(all_endpoints),
            "raw_findings": len(raw_findings),
            "persisted": persisted,
            "killed": killed,
        }

    async def _fetch(self, url: str, timeout: float = 15.0) -> str:
        async with _httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=False,
        ) as client:
            r = await client.get(url, headers=_BOUNTY_HEADERS)
            if r.is_success:
                return r.text
        return ""

    async def _crawl_target(self, base_url: str) -> tuple[list[str], list[str]]:
        """Use katana to crawl then segregate JS URLs from API endpoints."""
        from app.tools import katana as katana_tool

        results = await katana_tool.crawl(base_url, depth=3, timeout=90)
        js_urls = katana_tool.filter_js_urls(results)
        all_urls = [r.url for r in results if hasattr(r, "url")]

        # Endpoint: paths that look like API routes (contain /api/, /v1/, /graphql, etc.)
        api_pattern = re.compile(
            r'/(api|v[0-9]|graphql|rest|rpc|service|internal|admin|auth|user|account|payment|order)',
            re.IGNORECASE,
        )
        endpoints = [u for u in all_urls if api_pattern.search(u)]
        return js_urls, endpoints

    async def _probe_endpoints(self, endpoints: list[str]) -> list[dict]:
        """Probe endpoints with the bounty header and collect response metadata."""
        results = []
        async with _httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            verify=False,
            headers=_BOUNTY_HEADERS,
        ) as client:
            for url in endpoints:
                try:
                    r = await client.get(url)
                    body_preview = r.text[:500] if r.text else ""
                    results.append({
                        "url": url,
                        "status": r.status_code,
                        "content_type": r.headers.get("content-type", ""),
                        "body_preview": body_preview,
                        "headers": dict(r.headers),
                    })
                except Exception:
                    continue
        return results

    def _parse_llm_output(self, raw: str) -> list[dict]:
        """Extract JSON array from LLM response, tolerating markdown fences."""
        text = raw.strip()
        # Strip markdown fences
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        text = text.strip()

        if not text or text == "[]":
            return []

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            # Try to extract array substring
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    if isinstance(data, list):
                        return [d for d in data if isinstance(d, dict)]
                except Exception:
                    pass
        return []
