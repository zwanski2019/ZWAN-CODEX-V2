"""subfinder wrapper — subdomain enumeration."""
from __future__ import annotations

from app.tools.shell import run_json


async def enumerate_subdomains(domain: str, timeout: int = 120) -> list[str]:
    """Return list of discovered subdomains for a domain."""
    results = await run_json(
        f"subfinder -d {domain} -silent -json -timeout 30",
        timeout=timeout,
    )
    return [r["host"] for r in results if "host" in r]


async def enumerate_multi(domains: list[str], timeout: int = 180) -> list[str]:
    """Enumerate subdomains for multiple root domains."""
    all_subs: list[str] = []
    for domain in domains:
        subs = await enumerate_subdomains(domain, timeout=timeout)
        all_subs.extend(subs)
    return list(set(all_subs))
