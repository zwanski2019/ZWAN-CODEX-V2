"""httpx wrapper — live host probing + tech fingerprinting."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.tools.shell import run_json


@dataclass
class HostResult:
    url: str
    host: str
    ip: str = ""
    status_code: int = 0
    title: str = ""
    tech: list[str] = field(default_factory=list)
    server: str = ""
    content_length: int = 0
    cdn: str = ""
    webserver: str = ""
    raw: dict = field(default_factory=dict)


async def probe(hosts: list[str], timeout: int = 120) -> list[HostResult]:
    """Probe a list of hosts/URLs, return live ones with metadata."""
    if not hosts:
        return []
    host_list = "\n".join(hosts)
    # pipe hosts via stdin using process substitution trick
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(host_list)
        tmp = f.name

    try:
        results = await run_json(
            f"httpx -l {tmp} -silent -json -title -tech-detect -status-code "
            f"-ip -server -content-length -timeout 10 -threads 50",
            timeout=timeout,
        )
    finally:
        os.unlink(tmp)

    out: list[HostResult] = []
    for r in results:
        out.append(
            HostResult(
                url=r.get("url", ""),
                host=r.get("host", r.get("input", "")),
                ip=r.get("ip", ""),
                status_code=r.get("status_code", 0),
                title=r.get("title", ""),
                tech=r.get("tech", []),
                server=r.get("server", ""),
                content_length=r.get("content_length", 0),
                cdn=r.get("cdn", ""),
                webserver=r.get("webserver", ""),
                raw=r,
            )
        )
    return out
