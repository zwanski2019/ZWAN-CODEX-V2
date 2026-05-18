from __future__ import annotations

import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # engagement_id -> list of connected WebSocket clients
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, engagement_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[engagement_id].append(ws)

    def disconnect(self, engagement_id: str, ws: WebSocket) -> None:
        self._connections[engagement_id].remove(ws)

    async def broadcast(self, engagement_id: str, event: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections[engagement_id]:
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[engagement_id].remove(ws)

    async def broadcast_all(self, event: dict) -> None:
        for eng_id in list(self._connections):
            await self.broadcast(eng_id, event)


manager = ConnectionManager()
