"""Caido API client. Alternative to Burp Pro."""
from __future__ import annotations

import httpx

from app.config import settings


class CaidoClient:
    def __init__(self) -> None:
        # Caido uses a GraphQL API
        self.base = getattr(settings, "caido_api_url", "http://127.0.0.1:8080")
        self.key = getattr(settings, "caido_api_key", "")

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    async def _gql(self, query: str, variables: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base}/graphql",
                headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
            )
            r.raise_for_status()
            return r.json()

    async def get_requests(self, host_filter: str = "") -> list[dict]:
        """Retrieve captured requests from Caido's history."""
        if not self.enabled:
            return []
        query = """
        query GetRequests($filter: RequestsFilter) {
          requests(filter: $filter) { id host port path method status }
        }
        """
        variables = {"filter": {"host": {"like": f"%{host_filter}%"}}} if host_filter else {}
        data = await self._gql(query, variables)
        return data.get("data", {}).get("requests", [])


caido = CaidoClient()
