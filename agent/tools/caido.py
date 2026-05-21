"""
Caido proxy client for ZWAN-AGENT.

Integrates with Caido's GraphQL API to:
  - Pull HTTP history filtered by host (caido_history tool)
  - Create findings linked to captured requests (caido_create_finding tool)
  - Route CLI tools through Caido's intercept proxy (automatic via CAIDO_PROXY env)

Config (env vars):
  CAIDO_URL=http://127.0.0.1:8080       Caido UI/API URL (default)
  CAIDO_API_KEY=<from Caido Settings>   Bearer token: Settings → Users → API Keys
  CAIDO_PROXY=http://127.0.0.1:8080     Proxy addr for routing all CLI tool traffic
"""
from __future__ import annotations

import os
from typing import Any

import httpx

CAIDO_URL: str = os.environ.get("CAIDO_URL", "http://127.0.0.1:8080")
CAIDO_API_KEY: str = os.environ.get("CAIDO_API_KEY", "")
CAIDO_PROXY: str = os.environ.get("CAIDO_PROXY", "")

_GQL = f"{CAIDO_URL}/graphql"


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if CAIDO_API_KEY:
        h["Authorization"] = f"Bearer {CAIDO_API_KEY}"
    return h


def _check_errors(data: dict) -> None:
    errors = data.get("errors")
    if not errors:
        return
    first = errors[0]
    code = first.get("extensions", {}).get("CAIDO", {}).get("code", "")
    if code == "AUTHORIZATION":
        raise PermissionError(
            "Caido API key missing or invalid — set CAIDO_API_KEY env var "
            "(Caido → Settings → Users → API Keys)"
        )
    raise RuntimeError(f"Caido GraphQL error: {first.get('message', 'unknown')}")


async def alive() -> bool:
    """Return True if Caido daemon is reachable (no auth required)."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(CAIDO_URL, follow_redirects=True)
            return r.status_code == 200
    except Exception:
        return False


# ── History ───────────────────────────────────────────────────────────────────

_HISTORY_QUERY = """
query ZwanHistory($first: Int) {
  requests(first: $first) {
    edges {
      node {
        id
        host
        port
        method
        path
        query
        isTls
        length
      }
    }
  }
}
"""


async def history(limit: int = 50, host_filter: str = "") -> list[dict]:
    """
    Fetch recent HTTP requests from Caido's history.
    Raises PermissionError if CAIDO_API_KEY is missing/invalid.
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
    edges = data.get("data", {}).get("requests", {}).get("edges", [])
    rows: list[dict] = [e["node"] for e in edges]
    if host_filter:
        rows = [req for req in rows if host_filter.lower() in req.get("host", "").lower()]
    return rows


# ── Create Finding ────────────────────────────────────────────────────────────

_CREATE_FINDING_MUTATION = """
mutation ZwanCreateFinding($requestId: ID!, $input: CreateFindingInput!) {
  createFinding(requestId: $requestId, input: $input) {
    finding {
      id
      title
      host
      path
    }
    error {
      code
      message
    }
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
    The agent calls this when it confirms a vulnerability to surface it in Caido's UI.
    """
    input_data: dict[str, Any] = {"title": title, "reporter": reporter}
    if description:
        input_data["description"] = description
    if dedupe_key:
        input_data["dedupeKey"] = dedupe_key

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _GQL,
            json={
                "query": _CREATE_FINDING_MUTATION,
                "variables": {"requestId": request_id, "input": input_data},
            },
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()

    _check_errors(data)
    payload = data.get("data", {}).get("createFinding", {})
    if payload.get("error"):
        err = payload["error"]
        raise RuntimeError(f"Caido create_finding error [{err.get('code')}]: {err.get('message')}")
    return payload.get("finding", {})


# ── Formatting helpers ────────────────────────────────────────────────────────

def format_history_table(rows: list[dict]) -> str:
    """Render history rows as a markdown table for the planner."""
    if not rows:
        return "No requests in Caido history matching the filter. Check CAIDO_API_KEY."
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
            f"| {req.get('id', '?')} | {req.get('method', '?')} "
            f"| {scheme}://{req.get('host', '?')}:{port} "
            f"| {path[:55]} | {req.get('length', '-')} |"
        )
    return "\n".join(lines)
