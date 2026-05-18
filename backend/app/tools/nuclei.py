"""nuclei wrapper — runs ONLY Tier S template tags. Not the primary scanner."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.shell import run_json

# Only run templates relevant to Tier S vulns — not generic OWASP checks
TIER_S_TAGS = "oauth,jwt,desync,ssrf,ssti,prototype-pollution,graphql,cache"


@dataclass
class NucleiResult:
    template_id: str
    name: str
    severity: str
    host: str
    matched_at: str
    curl_command: str = ""
    description: str = ""
    raw: dict = field(default_factory=dict)


async def scan(targets: list[str], tags: str = TIER_S_TAGS, timeout: int = 300) -> list[NucleiResult]:
    """Run nuclei with Tier S tags only. Returns findings."""
    if not targets:
        return []
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(targets))
        tmp = f.name

    try:
        results = await run_json(
            f"nuclei -l {tmp} -tags {tags} -json -silent -timeout 10 -c 20 "
            f"-severity medium,high,critical",
            timeout=timeout,
        )
    finally:
        os.unlink(tmp)

    out: list[NucleiResult] = []
    for r in results:
        info = r.get("info", {})
        out.append(
            NucleiResult(
                template_id=r.get("template-id", ""),
                name=info.get("name", ""),
                severity=info.get("severity", "unknown"),
                host=r.get("host", ""),
                matched_at=r.get("matched-at", ""),
                curl_command=r.get("curl-command", ""),
                description=info.get("description", ""),
                raw=r,
            )
        )
    return out
