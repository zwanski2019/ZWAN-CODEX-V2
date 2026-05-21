"""
Async Playwright driver. One instance per AgentSession.

Stateful: holds a live chromium page across actions, captures XHR/fetch
endpoints touched along the way, and serializes the DOM into a numbered
element list for the planner to act on by index.

Never starts the browser process until start() is called — keeps dry-run
sessions truly network-free.
"""
from __future__ import annotations

import base64
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class Browser:
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw = None
        self._browser = None
        self._page = None
        self._last: list = []
        self.seen_endpoints: set[str] = set()

    async def start(self) -> None:
        if self._page is not None:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        self._page.on("request", self._on_request)

    def _on_request(self, req) -> None:
        try:
            if req.resource_type not in ("xhr", "fetch"):
                return
            u = urlparse(req.url)
            if u.path:
                self.seen_endpoints.add(f"{req.method} {u.scheme}://{u.netloc}{u.path}")
        except Exception:
            pass

    @property
    def started(self) -> bool:
        return self._page is not None

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    def current_host(self) -> str:
        return urlparse(self.current_url).hostname or ""

    async def goto(self, url: str) -> None:
        await self._page.goto(url, wait_until="domcontentloaded", timeout=20_000)

    async def observe(self, limit: int = 60) -> list[dict]:
        """Visible interactive elements, numbered for the planner."""
        els = await self._page.query_selector_all(
            "a, button, input, textarea, select, [role=button], [onclick]"
        )
        kept: list = []
        out: list[dict] = []
        for e in els:
            try:
                if not await e.is_visible():
                    continue
                tag = (await e.evaluate("el => el.tagName")) or ""
                placeholder = await e.get_attribute("placeholder")
                text = (await e.inner_text()) or placeholder or ""
                out.append({
                    "id": len(kept),
                    "tag": tag.lower(),
                    "type": await e.get_attribute("type"),
                    "name": await e.get_attribute("name"),
                    "text": text.strip()[:80],
                })
                kept.append(e)
                if len(kept) >= limit:
                    break
            except Exception:
                continue
        self._last = kept
        return out

    async def act(self, action: dict) -> str:
        op = action.get("op", "")
        if op == "goto":
            url = action.get("url", "")
            if not url:
                raise ValueError("goto requires 'url'")
            await self.goto(url)
            return f"navigated to {url}"
        if op == "back":
            await self._page.go_back()
            return "navigated back"
        if op == "extract":
            text = await self._page.inner_text("body")
            return text[:6000]
        if op == "screenshot":
            png = await self._page.screenshot()
            return base64.b64encode(png).decode("ascii")
        if op in ("click", "type", "submit"):
            idx = action.get("id", -1)
            if not isinstance(idx, int) or not (0 <= idx < len(self._last)):
                raise IndexError(f"no element id {idx} (have {len(self._last)})")
            e = self._last[idx]
            if op == "click":
                await e.click()
                return f"clicked element {idx}"
            if op == "type":
                await e.fill(str(action.get("value", "")))
                return f"typed into element {idx}"
            if op == "submit":
                await e.press("Enter")
                return f"submitted element {idx}"
        raise ValueError(f"unknown browser op: {op!r}")

    def discovered(self) -> list[str]:
        return sorted(self.seen_endpoints)

    async def snap(self) -> str | None:
        """Best-effort PNG snapshot as base64. Returns None on failure."""
        if not self._page:
            return None
        try:
            png = await self._page.screenshot(full_page=False)
            return base64.b64encode(png).decode("ascii")
        except Exception:
            return None

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
        finally:
            if self._pw:
                await self._pw.stop()
            self._browser = None
            self._page = None
            self._pw = None
