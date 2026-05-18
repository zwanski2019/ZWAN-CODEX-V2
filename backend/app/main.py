from __future__ import annotations

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents as agents_router
from app.api import engagements as engagements_router
from app.api import findings as findings_router
from app.api import loot as loot_router
from app.api import system as system_router
from app.api import settings_api as settings_router
from app.config import settings
from app.db.base import engine
from app.db.models import Base
from app.ws.manager import manager

# Import all agents so @register_agent decorators fire
import app.agents.recon  # noqa: F401
import app.agents.js_miner  # noqa: F401
import app.agents.oauth_chain  # noqa: F401
import app.agents.desync  # noqa: F401
import app.agents.race  # noqa: F401
import app.agents.ssrf  # noqa: F401
import app.agents.agentic_target  # noqa: F401
import app.agents.chain_hunter  # noqa: F401
import app.agents.validator  # noqa: F401
import app.agents.report  # noqa: F401
import app.agents.zeroday_scanner  # noqa: F401

app = FastAPI(
    title="ZWAN-CODEX-V2",
    description="Agentic bug bounty platform",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(engagements_router.router, prefix="/api")
app.include_router(findings_router.router, prefix="/api")
app.include_router(agents_router.router, prefix="/api")
app.include_router(loot_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(system_router.router)


@app.on_event("startup")
async def on_startup() -> None:
    # Auto-create tables if Alembic hasn't run yet (dev convenience)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}


@app.websocket("/ws/{engagement_id}")
async def ws_engagement(websocket: WebSocket, engagement_id: str) -> None:
    await manager.connect(engagement_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            # Echo back with type=echo for M1 verification
            await websocket.send_text(json.dumps({"type": "echo", "data": data}))
    except WebSocketDisconnect:
        manager.disconnect(engagement_id, websocket)


@app.post("/api/engagements/{engagement_id}/start")
async def start_hunt(engagement_id: str) -> dict:
    """Enqueue an engagement for processing via the Arq worker."""
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await pool.enqueue_job("hunt_engagement", engagement_id)
    await pool.aclose()
    return {"queued": True, "engagement_id": engagement_id}
