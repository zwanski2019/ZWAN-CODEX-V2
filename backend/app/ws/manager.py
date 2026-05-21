from __future__ import annotations

import json
import asyncio
from collections import defaultdict, deque
from datetime import datetime

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

_GLOBAL = "_global"
_RECENT_MAX = 200
_REDIS_CHANNEL = "ws:events"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._recent: deque[dict] = deque(maxlen=_RECENT_MAX)
        self._redis: aioredis.Redis | None = None

    # ── Redis pub/sub ──────────────────────────────────────────────────────

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def publish(self, engagement_id: str, event: dict) -> None:
        """Publish event to Redis so any process can broadcast it."""
        r = await self._get_redis()
        payload = json.dumps({"engagement_id": engagement_id, "event": event})
        await r.publish(_REDIS_CHANNEL, payload)

    async def start_subscriber(self) -> None:
        """Background task: subscribe to Redis and forward to local WS clients."""
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(_REDIS_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await self._deliver(data["engagement_id"], data["event"])
            except Exception:
                pass

    # ── Local WebSocket delivery ───────────────────────────────────────────

    async def connect(self, engagement_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[engagement_id].append(ws)
        if engagement_id == _GLOBAL:
            for ev in self._recent:
                try:
                    await ws.send_text(json.dumps(ev))
                except Exception:
                    break

    def disconnect(self, engagement_id: str, ws: WebSocket) -> None:
        try:
            self._connections[engagement_id].remove(ws)
        except ValueError:
            pass

    async def _deliver(self, engagement_id: str, event: dict) -> None:
        """Send to local WebSocket connections for this engagement + global feed."""
        dead: list[WebSocket] = []
        for ws in self._connections[engagement_id]:
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections[engagement_id].remove(ws)
            except ValueError:
                pass

        if engagement_id != _GLOBAL:
            enriched = {
                **event,
                "engagement_id": engagement_id,
                "ts": event.get("ts") or datetime.utcnow().isoformat(),
            }
            self._recent.append(enriched)

            dead_g: list[WebSocket] = []
            for ws in self._connections[_GLOBAL]:
                try:
                    await ws.send_text(json.dumps(enriched))
                except Exception:
                    dead_g.append(ws)
            for ws in dead_g:
                try:
                    self._connections[_GLOBAL].remove(ws)
                except ValueError:
                    pass

    async def broadcast(self, engagement_id: str, event: dict) -> None:
        """Publish via Redis so all processes (worker, backend) route through one path."""
        await self.publish(engagement_id, event)

    async def broadcast_all(self, event: dict) -> None:
        for eng_id in list(self._connections):
            await self.broadcast(eng_id, event)

    @property
    def active_engagements(self) -> list[str]:
        return [k for k, v in self._connections.items() if v and k != _GLOBAL]


manager = ConnectionManager()
