"""desync agent — stub (M1). Full implementation: M2+."""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.orchestrator import register_agent


@register_agent
class DesyncAgent(BaseAgent):
    name = "desync"

    async def _execute(self) -> dict:
        await self._emit("trace", {"message": "stub — not yet implemented"})
        return {"status": "stub"}
