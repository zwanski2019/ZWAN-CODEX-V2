"""Base class all agents inherit from."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, AgentStatus, Engagement
from app.llm.router import LLMRouter
from app.ws.manager import manager


class BaseAgent(ABC):
    name: str = "base"

    def __init__(
        self,
        engagement: Engagement,
        db: AsyncSession,
        llm: LLMRouter,
    ) -> None:
        self.engagement = engagement
        self.db = db
        self.llm = llm
        self._run: AgentRun | None = None
        self._trace: list[dict] = []

    async def _init_run(self) -> None:
        run_id = str(uuid.uuid4())
        self._run = AgentRun(
            id=run_id,
            engagement_id=self.engagement.id,
            agent_name=self.name,
            status=AgentStatus.RUNNING,
        )
        self.db.add(self._run)
        await self.db.flush()
        # Set started_at via DB to avoid timezone-naive/aware conflicts
        await self.db.execute(
            text("UPDATE agent_runs SET started_at = now() WHERE id = :id"),
            {"id": run_id},
        )
        await self.db.commit()

    async def _emit(self, event_type: str, data: Any) -> None:
        event = {"agent": self.name, "type": event_type, "data": data}
        self._trace.append(event)
        await manager.broadcast(self.engagement.id, event)

    async def _finish_run(self, output: dict, error: str | None = None) -> None:
        if not self._run:
            return
        self._run.status = AgentStatus.FAILED if error else AgentStatus.DONE
        self._run.output_data = output
        self._run.trace = self._trace
        self._run.error = error
        self._run.llm_cost_usd = self.llm.spent
        await self.db.flush()
        await self.db.execute(
            text("UPDATE agent_runs SET finished_at = now() WHERE id = :id"),
            {"id": self._run.id},
        )
        await self.db.commit()

    async def run(self) -> dict:
        await self._init_run()
        await self._emit("started", {"agent": self.name})
        try:
            result = await self._execute()
            await self._finish_run(result)
            await self._emit("done", result)
            return result
        except Exception as exc:
            await self._finish_run({}, error=str(exc))
            await self._emit("error", {"message": str(exc)})
            raise

    @abstractmethod
    async def _execute(self) -> dict:
        ...
