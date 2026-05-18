"""ChainHunterAgent — finds exploit chains across all existing findings."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Finding, FindingStatus, Severity

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "chain_hunter.md"

_CHAIN_MULTIPLIERS = {
    ("ssrf", "recon"): ("SSRF to Internal Service", "critical", "SSRF primitive + internal endpoint map = full internal pivot"),
    ("oauth_chain", "recon"): ("OAuth ATO via Subdomain", "critical", "OAuth redirect_uri bypass on discovered subdomain = account takeover"),
    ("js_miner", "oauth_chain"): ("Leaked OAuth Secret", "critical", "Client secret from JS + OAuth endpoint = token forgery"),
    ("ssrf", "js_miner"): ("SSRF via Leaked Internal Endpoint", "high", "SSRF to internal endpoint discovered in JS bundle"),
    ("agentic_target", "ssrf"): ("LLM-Triggered SSRF", "critical", "Prompt injection causes AI tool to make SSRF request"),
    ("race", "oauth_chain"): ("Race on OAuth Token Exchange", "high", "Race condition on token endpoint = duplicate access tokens"),
    ("desync", "recon"): ("Desync Cache Poison on High-Value Host", "high", "Request smuggling on interesting subdomain = cache poisoning"),
}


@register_agent
class ChainHunterAgent(BaseAgent):
    name = "chain_hunter"

    async def _execute(self) -> dict:
        # Load all pending/valid findings for this engagement
        result = await self.db.execute(
            select(Finding).where(
                Finding.engagement_id == self.engagement.id,
                Finding.status.in_([FindingStatus.PENDING, FindingStatus.VALID]),
            )
        )
        findings = list(result.scalars().all())

        if len(findings) < 2:
            await self._emit("trace", {"message": f"Only {len(findings)} findings — need 2+ to chain"})
            return {"chains": 0}

        await self._emit("trace", {"message": f"Analyzing {len(findings)} findings for chains"})

        # Summarize findings for LLM
        summary = [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity,
                "description": f.description[:200],
                "agent": f.meta.get("agent", "unknown") if f.meta else "unknown",
            }
            for f in findings
        ]

        chain_prompt = (
            f"Analyze these {len(findings)} findings and identify exploit chains:\n\n"
            f"{json.dumps(summary, indent=2)}\n\n"
            "For each viable chain, output JSON with: title, finding_ids, chain_steps, combined_cvss, impact, poc_sketch"
        )

        try:
            analysis, _ = await self.llm.complete(
                model=settings.llm_heavy,
                system=_PROMPT_PATH.read_text(),
                messages=[{"role": "user", "content": chain_prompt}],
                max_tokens=4096,
            )
        except Exception as e:
            await self._emit("trace", {"message": f"LLM chain analysis failed: {e}"})
            return {"chains": 0, "error": str(e)}

        # Parse chains from LLM output
        chains = self._parse_chains(analysis, findings)
        await self._emit("trace", {"message": f"LLM identified {len(chains)} potential chains"})

        # Also apply rule-based chain detection
        rule_chains = self._rule_based_chains(findings)
        chains.extend(rule_chains)

        # Persist chain findings
        for chain in chains:
            cvss = min(float(chain.get("combined_cvss", 7.0)), 10.0)
            sev = Severity.CRITICAL if cvss >= 9.0 else Severity.HIGH
            finding = Finding(
                id=str(uuid.uuid4()),
                engagement_id=self.engagement.id,
                title=f"[CHAIN] {chain['title']}",
                severity=sev,
                status=FindingStatus.PENDING,
                cvss_score=cvss,
                description=chain.get("impact", ""),
                reproducer="\n".join(chain.get("chain_steps", [])),
                impact=chain.get("impact", ""),
                chain_ids=chain.get("finding_ids", []),
                meta={"llm_analysis": analysis[:2000], "chain_data": chain},
            )
            self.db.add(finding)
        await self.db.commit()

        await self._emit("trace", {"message": f"Chain hunting done: {len(chains)} chains found"})
        return {"chains": len(chains), "chain_titles": [c["title"] for c in chains]}

    def _parse_chains(self, llm_output: str, findings: list[Finding]) -> list[dict]:
        chains: list[dict] = []
        try:
            # Try to extract JSON from LLM output
            import re
            json_match = re.search(r'\[[\s\S]*\]', llm_output)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "title" in item:
                            chains.append(item)
        except Exception:
            pass
        return chains

    def _rule_based_chains(self, findings: list[Finding]) -> list[dict]:
        chains: list[dict] = []
        agent_map: dict[str, list[Finding]] = {}
        for f in findings:
            agent = (f.meta or {}).get("agent", "")
            if agent:
                agent_map.setdefault(agent, []).append(f)

        for (a1, a2), (title, sev, impact) in _CHAIN_MULTIPLIERS.items():
            if a1 in agent_map and a2 in agent_map:
                ids = [agent_map[a1][0].id, agent_map[a2][0].id]
                chains.append({
                    "title": title,
                    "finding_ids": ids,
                    "chain_steps": [
                        f"Step 1: Exploit {agent_map[a1][0].title}",
                        f"Step 2: Leverage access to exploit {agent_map[a2][0].title}",
                    ],
                    "combined_cvss": 9.5 if sev == "critical" else 7.5,
                    "impact": impact,
                    "source": "rule-based",
                })
        return chains
