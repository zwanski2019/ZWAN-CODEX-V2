"""System status + graceful stop — local use only (binds to 127.0.0.1)."""
from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/system", tags=["system"])

_PID_DIR = Path(__file__).parents[3] / ".pids"
_IN_DOCKER = Path("/.dockerenv").exists()


def _read_pid(name: str) -> int | None:
    p = _PID_DIR / f"{name}.pid"
    try:
        return int(p.read_text().strip())
    except Exception:
        return None


def _is_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


async def _http_up(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(url)
            return r.status_code in (200, 307)
    except Exception:
        return False


async def _worker_up_via_redis() -> bool:
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        val = await r.get("arq:queue:health-check")
        await r.aclose()
        return val is not None
    except Exception:
        return False


@router.get("/status")
async def system_status() -> dict:
    if _IN_DOCKER:
        # Docker mode: worker via Redis health-check key, frontend via HTTP
        worker_up, frontend_up = await asyncio.gather(
            _worker_up_via_redis(),
            _http_up("http://frontend:3000/"),
        )
        return {
            "backend": {"up": True, "pid": os.getpid()},
            "worker": {"up": worker_up, "pid": None},
            "frontend": {"up": frontend_up, "pid": None},
        }

    # Native dev mode: check PID files
    worker_pid = _read_pid("worker")
    frontend_pid = _read_pid("frontend")
    frontend_up = await _http_up(f"http://127.0.0.1:{settings.frontend_port}/")

    return {
        "backend": {"up": True, "pid": os.getpid()},
        "worker": {"up": _is_alive(worker_pid), "pid": worker_pid},
        "frontend": {"up": frontend_up or _is_alive(frontend_pid), "pid": frontend_pid},
    }


@router.post("/stop")
async def system_stop() -> dict:
    """Kill worker + frontend, then self-terminate backend after response."""
    stopped: list[str] = []

    for name in ("worker", "frontend"):
        pid = _read_pid(name)
        if _is_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(name)
            except Exception:
                pass

    # Schedule backend self-termination after we send the response
    async def _die() -> None:
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_die())
    stopped.append("backend")

    return {"stopped": stopped, "message": "All services stopping"}
