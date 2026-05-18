"""katana wrapper — JS-aware crawler for endpoint + JS bundle discovery."""
from __future__ import annotations

from dataclasses import dataclass

from app.tools.shell import run_json


@dataclass
class CrawlResult:
    url: str
    source: str = ""
    tag: str = ""
    attribute: str = ""


async def crawl(target_url: str, depth: int = 3, timeout: int = 180) -> list[CrawlResult]:
    """Crawl a URL, return all discovered endpoints and JS files."""
    results = await run_json(
        f"katana -u {target_url} -d {depth} -silent -json "
        f"-jc -aff -timeout 10 -c 10",
        timeout=timeout,
    )
    out: list[CrawlResult] = []
    for r in results:
        req = r.get("request", {})
        out.append(
            CrawlResult(
                url=req.get("endpoint", r.get("endpoint", "")),
                source=r.get("source", ""),
                tag=r.get("tag", ""),
                attribute=r.get("attribute", ""),
            )
        )
    return out


def filter_js_urls(results: list[CrawlResult]) -> list[str]:
    return [r.url for r in results if r.url.endswith(".js") or ".js?" in r.url]
