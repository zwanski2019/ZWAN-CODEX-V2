"""ffuf wrapper — endpoint fuzzing."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.shell import run


@dataclass
class FfufResult:
    url: str
    status: int
    length: int
    words: int
    lines: int


async def fuzz(
    url_template: str,
    wordlist: str = "/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt",
    filter_codes: str = "404,400,403",
    timeout: int = 180,
) -> list[FfufResult]:
    """
    Fuzz URL with FUZZ placeholder. Returns non-filtered results.
    url_template example: "https://target.com/FUZZ"
    """
    import json as _json
    stdout, _, _ = await run(
        f"ffuf -u {url_template} -w {wordlist} "
        f"-fc {filter_codes} -json -t 40 -timeout 10 -s",
        timeout=timeout,
    )
    if not stdout.strip():
        return []
    try:
        data = _json.loads(stdout)
    except _json.JSONDecodeError:
        return []

    out: list[FfufResult] = []
    for r in data.get("results", []):
        out.append(
            FfufResult(
                url=r.get("url", ""),
                status=r.get("status", 0),
                length=r.get("length", 0),
                words=r.get("words", 0),
                lines=r.get("lines", 0),
            )
        )
    return out
