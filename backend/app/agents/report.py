"""ReportAgent — generates submission-ready markdown for every VALID finding."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent
from app.config import settings
from app.db.models import Finding, FindingStatus

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "report.md"


@register_agent
class ReportAgent(BaseAgent):
    name = "report"

    async def _execute(self) -> dict:
        system_prompt = _PROMPT_PATH.read_text()

        result = await self.db.execute(
            select(Finding).where(
                Finding.engagement_id == self.engagement.id,
                Finding.status == FindingStatus.VALID,
                Finding.report_md == "",
            )
        )
        findings = list(result.scalars().all())

        if not findings:
            await self._emit("trace", {"message": "No VALID findings without reports"})
            return {"reports_generated": 0}

        await self._emit("trace", {"message": f"Generating reports for {len(findings)} valid findings"})
        generated = 0

        for finding in findings:
            await self._emit("trace", {"message": f"Reporting: {finding.title[:60]}"})
            try:
                report_md, cvss_score, cvss_vector = await self._generate_report(finding, system_prompt)
                finding.report_md = report_md
                if cvss_score:
                    finding.cvss_score = cvss_score
                if cvss_vector:
                    finding.cvss_vector = cvss_vector
                generated += 1
                await self._emit("trace", {"message": f"Report done: {finding.title[:50]}"})
            except Exception as e:
                await self._emit("trace", {"message": f"Report error for {finding.title[:40]}: {e}"})

        await self.db.commit()
        await self._emit("trace", {"message": f"Reporting done: {generated} reports generated"})
        return {"reports_generated": generated}

    async def _generate_report(self, finding: Finding, system_prompt: str) -> tuple[str, float | None, str | None]:
        context = {
            "title": finding.title,
            "severity": finding.severity,
            "description": finding.description,
            "reproducer": finding.reproducer[:1000],
            "impact": finding.impact,
            "http_transcript": finding.http_transcript[:2000],
            "existing_cvss": finding.cvss_score,
        }

        response, _ = await self.llm.complete(
            model=settings.llm_heavy,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Write the full submission-ready report for this finding:\n"
                    f"{json.dumps(context, indent=2)}\n\n"
                    "Return JSON: {\"report_md\": \"...\", \"cvss_score\": 0.0, \"cvss_vector\": \"CVSS:3.1/...\"}"
                ),
            }],
            max_tokens=4096,
            temperature=0.1,
        )

        # Parse JSON response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            parsed = json.loads(json_match.group())
            return (
                parsed.get("report_md", response),
                parsed.get("cvss_score"),
                parsed.get("cvss_vector"),
            )

        return response, None, None
