"""
Caido proxy client for ZWAN-AGENT.

Auth: Caido uses a device-code OAuth flow. No API key required for the free tier.
The agent calls startAuthenticationFlow, the user approves on dashboard.caido.io,
and the resulting token is cached in memory for the session.

Config (env vars):
  CAIDO_URL=http://127.0.0.1:8080       Caido UI/API URL (default)
  CAIDO_API_KEY=<optional>              Pre-set Bearer token (skips device flow)
  CAIDO_PROXY=http://127.0.0.1:8080     Routes all CLI tool traffic through Caido
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Awaitable, Callable

import httpx
import websockets

CAIDO_URL: str = os.environ.get("CAIDO_URL", "http://127.0.0.1:8080")
CAIDO_API_KEY: str = os.environ.get("CAIDO_API_KEY", "")
CAIDO_PROXY: str = os.environ.get("CAIDO_PROXY", "")

_GQL = f"{CAIDO_URL}/graphql"
_WS_GQL = _GQL.replace("http://", "ws://").replace("https://", "wss://")

# In-memory token cache — populated by the device auth flow
_cached_token: str = ""
_cached_refresh_token: str = ""


def _active_token() -> str:
    return _cached_token or CAIDO_API_KEY


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    tok = _active_token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _check_errors(data: dict) -> None:
    errors = data.get("errors")
    if not errors:
        return
    first = errors[0]
    code = first.get("extensions", {}).get("CAIDO", {}).get("code", "")
    if code == "AUTHORIZATION":
        raise PermissionError(
            "Caido token missing or invalid — run /api/caido/login to authenticate"
        )
    raise RuntimeError(f"Caido GraphQL error: {first.get('message', 'unknown')}")


# ── Connectivity ──────────────────────────────────────────────────────────────

async def alive() -> bool:
    """Return True if Caido daemon is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(CAIDO_URL, follow_redirects=True)
            return r.status_code == 200
    except Exception:
        return False


# ── Device-code auth flow ─────────────────────────────────────────────────────

_START_FLOW = """
mutation CaidoStartAuth {
  startAuthenticationFlow {
    request { id userCode verificationUrl expiresAt }
    error { __typename }
  }
}
"""


async def start_device_flow() -> dict:
    """
    Start the Caido device auth flow.
    Returns {id, userCode, verificationUrl, expiresAt}.
    The user must visit verificationUrl and approve within ~10 minutes.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(_GQL, json={"query": _START_FLOW},
                              headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
    req = (data.get("data") or {}).get("startAuthenticationFlow", {}).get("request") or {}
    return req


_WAIT_SUB = """
subscription CaidoWaitToken($id: ID!) {
  createdAuthenticationToken(requestId: $id) {
    token { accessToken refreshToken { value } expiresAt scopes }
  }
}
"""


async def wait_for_token(
    request_id: str,
    on_token: Callable[[str, str], Awaitable[None]],
    timeout_sec: int = 600,
) -> None:
    """
    Subscribe to Caido's GraphQL WS and wait for the user to approve the device flow.
    Calls on_token(access_token, refresh_token) when auth completes.
    """
    global _cached_token, _cached_refresh_token

    sub_msg = json.dumps({
        "type": "subscribe",
        "id": "caido-auth",
        "payload": {
            "query": _WAIT_SUB,
            "variables": {"id": request_id},
        },
    })

    try:
        async with websockets.connect(
            _WS_GQL,
            subprotocols=["graphql-transport-ws"],
            open_timeout=10,
        ) as ws:
            await ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if ack.get("type") not in ("connection_ack", "ka"):
                raise RuntimeError(f"Unexpected WS ack: {ack}")

            await ws.send(sub_msg)

            deadline = asyncio.get_event_loop().time() + timeout_sec
            while asyncio.get_event_loop().time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
                msg = json.loads(raw)
                if msg.get("type") == "next":
                    tok = (
                        msg.get("payload", {})
                        .get("data", {})
                        .get("createdAuthenticationToken", {})
                        .get("token", {})
                    )
                    access = tok.get("accessToken", "")
                    refresh = (tok.get("refreshToken") or {}).get("value", "")
                    if access:
                        _cached_token = access
                        _cached_refresh_token = refresh
                        await on_token(access, refresh)
                        return
    except asyncio.TimeoutError:
        raise TimeoutError("Caido auth timed out — user did not approve within the window")


# ── HTTP History ──────────────────────────────────────────────────────────────

_HISTORY_QUERY = """
query ZwanHistory($first: Int) {
  requests(first: $first) {
    edges {
      node { id host port method path query isTls length }
    }
  }
}
"""


async def history(limit: int = 50, host_filter: str = "") -> list[dict]:
    """
    Fetch recent HTTP requests from Caido's history.
    Requires a full-scope token (from device flow or CAIDO_API_KEY).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _GQL,
            json={"query": _HISTORY_QUERY, "variables": {"first": limit}},
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
    _check_errors(data)
    edges = (data.get("data") or {}).get("requests", {}).get("edges", [])
    rows: list[dict] = [e["node"] for e in edges]
    if host_filter:
        rows = [req for req in rows if host_filter.lower() in req.get("host", "").lower()]
    return rows


# ── Create Finding ────────────────────────────────────────────────────────────

_CREATE_FINDING = """
mutation ZwanCreateFinding($requestId: ID!, $input: CreateFindingInput!) {
  createFinding(requestId: $requestId, input: $input) {
    finding { id title host path }
    error { __typename }
  }
}
"""


async def create_finding(
    request_id: str,
    title: str,
    description: str = "",
    reporter: str = "ZWAN-AGENT",
    dedupe_key: str = "",
) -> dict:
    """
    Create a Caido finding linked to a captured request ID.
    The agent calls this when it confirms a vulnerability.
    """
    input_data: dict = {"title": title, "reporter": reporter}
    if description:
        input_data["description"] = description
    if dedupe_key:
        input_data["dedupeKey"] = dedupe_key

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _GQL,
            json={"query": _CREATE_FINDING, "variables": {"requestId": request_id, "input": input_data}},
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
    _check_errors(data)
    payload = (data.get("data") or {}).get("createFinding", {})
    if payload.get("error"):
        raise RuntimeError(f"Caido finding error: {payload['error']}")
    return payload.get("finding", {})


# ── Formatting ────────────────────────────────────────────────────────────────

def format_history_table(rows: list[dict]) -> str:
    if not rows:
        return "No requests in Caido history. Authenticate first with /api/caido/login."
    lines = [
        "| ID | Method | Host | Path | Len |",
        "|----|--------|------|------|-----|",
    ]
    for req in rows[:40]:
        path = req.get("path", "/")
        if req.get("query"):
            path += "?" + req["query"]
        scheme = "https" if req.get("isTls") else "http"
        port = req.get("port", 443 if req.get("isTls") else 80)
        lines.append(
            f"| {req.get('id','?')} | {req.get('method','?')} "
            f"| {scheme}://{req.get('host','?')}:{port} "
            f"| {path[:55]} | {req.get('length','-')} |"
        )
    return "\n".join(lines)
