"""ValidatorAgent — THE GATE. Adversarial review of every pending finding."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Finding, FindingStatus, Severity

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "validator.md"

# Auto-kill rules (no LLM call needed)
_AUTO_KILL_TITLES = [
    "missing security header", "clickjacking", "username enumeration",
    "rate limit", "ssl", "tls version", "cookie without httponly",
    "cookie without secure", "cors", "self-xss", "csp",
    "x-frame-options", "content-type-options",
]

_AUTO_KILL_SEVERITIES = {Severity.LOW, Severity.INFO}


def _auto_kill_check(finding: Finding) -> str | None:
    """Return kill reason if finding is trivially invalid, else None."""
    if finding.severity in _AUTO_KILL_SEVERITIES:
        return f"Severity {finding.severity} — below CVSS 7.0 gate"

    title_lower = finding.title.lower()
    for pattern in _AUTO_KILL_TITLES:
        if pattern in title_lower:
            return f"Auto-kill: matches known-rejected pattern '{pattern}'"

    if finding.cvss_score and finding.cvss_score < 7.0:
        return f"CVSS {finding.cvss_score:.1f} < 7.0 gate"

    return None


@register_agent
class ValidatorAgent(BaseAgent):
    name = "validator"

    async def _execute(self) -> dict:
        system_prompt = _PROMPT_PATH.read_text()

        # Load all PENDING findings for this engagement
        result = await self.db.execute(
            select(Finding).where(
                Finding.engagement_id == self.engagement.id,
                Finding.status == FindingStatus.PENDING,
            )
        )
        findings = list(result.scalars().all())

        if not findings:
            await self._emit("trace", {"message": "No pending findings to validate"})
            return {"validated": 0, "killed": 0, "valid": 0}

        await self._emit("trace", {"message": f"Validating {len(findings)} pending findings"})

        killed = 0
        valid = 0
        needs_review = 0

        for finding in findings:
            await self._emit("trace", {"message": f"Validating: {finding.title[:60]}"})

            # Fast auto-kill check
            kill_reason = _auto_kill_check(finding)
            if kill_reason:
                finding.status = FindingStatus.KILLED
                finding.validator_reasoning = f"AUTO-KILL: {kill_reason}"
                killed += 1
                await self._emit("trace", {"message": f"KILLED (auto): {finding.title[:50]}"})
                continue

            # LLM adversarial review
            verdict, reasoning = await self._llm_review(finding, system_prompt)

            finding.validator_reasoning = reasoning
            if verdict == "VALID":
                finding.status = FindingStatus.VALID
                valid += 1
                await self._emit("trace", {"message": f"VALID: {finding.title[:50]}"})
            elif verdict == "KILL":
                finding.status = FindingStatus.KILLED
                killed += 1
                await self._emit("trace", {"message": f"KILLED (LLM): {finding.title[:50]}"})
            else:
                finding.status = FindingStatus.NEEDS_REVIEW
                needs_review += 1
                await self._emit("trace", {"message": f"NEEDS-REVIEW: {finding.title[:50]}"})

        await self.db.commit()

        kill_rate = killed / len(findings) * 100 if findings else 0
        await self._emit("trace", {
            "message": f"Validation complete: {valid} valid, {killed} killed ({kill_rate:.0f}%), {needs_review} needs review",
        })

        return {
            "validated": len(findings),
            "valid": valid,
            "killed": killed,
            "needs_review": needs_review,
            "kill_rate_pct": round(kill_rate, 1),
        }

    async def _llm_review(self, finding: Finding, system_prompt: str) -> tuple[str, str]:
        """Run adversarial LLM review. Returns (verdict, reasoning)."""
        finding_context = {
            "title": finding.title,
            "severity": finding.severity,
            "cvss_score": finding.cvss_score,
            "description": finding.description[:500],
            "reproducer": finding.reproducer[:500],
            "impact": finding.impact[:300],
        }

        messages = [{
            "role": "user",
            "content": (
                f"Review this finding:\n{json.dumps(finding_context, indent=2)}\n\n"
                "Answer the four gate questions and output EXACTLY one of: VALID, KILL, or NEEDS-MANUAL-REVIEW "
                "on the first line, then your reasoning."
            ),
        }]

        try:
            response, _ = await self.llm.complete(
                model=settings.llm_heavy,
                system=system_prompt,
                messages=messages,
                max_tokens=1500,
                temperature=0.1,
            )
            lines = response.strip().splitlines()
            verdict_line = lines[0].strip().upper() if lines else "NEEDS-MANUAL-REVIEW"
            reasoning = "\n".join(lines[1:]).strip() if len(lines) > 1 else response

            if "VALID" in verdict_line and "KILL" not in verdict_line:
                verdict = "VALID"
            elif "KILL" in verdict_line:
                verdict = "KILL"
            else:
                verdict = "NEEDS-MANUAL-REVIEW"

            return verdict, reasoning

        except Exception as e:
            return "NEEDS-MANUAL-REVIEW", f"LLM review failed: {e}"
