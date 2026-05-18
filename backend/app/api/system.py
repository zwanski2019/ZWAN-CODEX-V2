"""System status + graceful stop — local use only (binds to 127.0.0.1)."""
from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/system", tags=["system"])

_PID_DIR = Path(__file__).parents[3] / ".pids"


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


@router.get("/status")
async def system_status() -> dict:
    backend_pid = _read_pid("backend")
    worker_pid = _read_pid("worker")
    frontend_pid = _read_pid("frontend")

    # Check frontend reachability
    frontend_up = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"http://127.0.0.1:{settings.frontend_port}/")
            frontend_up = r.status_code in (200, 307)
    except Exception:
        pass

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
