from __future__ import annotations

import gzip
import hashlib
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from pathlib import Path

import aiosqlite

_DB_PATH = Path(os.environ.get("ZWAN_AUDIT_DB", Path.home() / ".zwan-codex" / "audit.db"))
_STORE_OUTPUT = os.environ.get("ZWAN_STORE_OUTPUT", "0") == "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    goal        TEXT,
    mode        TEXT,
    scope_hash  TEXT,
    ended_at    TEXT,
    summary     TEXT
);
CREATE TABLE IF NOT EXISTS commands (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    ts            TEXT NOT NULL,
    tool          TEXT,
    rendered_cmd  TEXT,
    tier          TEXT,
    needs_root    INTEGER,
    decision      TEXT,
    approved_by   TEXT,
    target        TEXT,
    exit_code     INTEGER,
    duration_ms   INTEGER,
    stdout_hash   TEXT,
    stderr_hash   TEXT,
    blocked_reason TEXT
);
CREATE TABLE IF NOT EXISTS outputs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    cmd_id  TEXT NOT NULL,
    stream  TEXT NOT NULL,
    data    BLOB
);
"""


@asynccontextmanager
async def _db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(_DB_PATH)
    try:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn
    finally:
        await conn.close()


async def session_open(goal: str, mode: str, scope_hash: str) -> str:
    sid = str(uuid.uuid4())
    async with _db() as db:
        await db.execute(
            "INSERT INTO sessions (id, started_at, goal, mode, scope_hash) VALUES (?, ?, ?, ?, ?)",
            (sid, _now(), goal, mode, scope_hash),
        )
        await db.commit()
    return sid


async def session_close(session_id: str, summary: str) -> None:
    async with _db() as db:
        await db.execute(
            "UPDATE sessions SET ended_at=?, summary=? WHERE id=?",
            (_now(), summary, session_id),
        )
        await db.commit()


async def command_log(
    session_id: str,
    tool: str,
    rendered_cmd: str,
    tier: str,
    needs_root: bool,
    decision: str,
    targets: list[str],
    blocked_reason: str | None = None,
) -> str:
    cid = str(uuid.uuid4())
    async with _db() as db:
        await db.execute(
            """INSERT INTO commands
               (id, session_id, ts, tool, rendered_cmd, tier, needs_root, decision, target, blocked_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, session_id, _now(), tool, rendered_cmd, tier,
             int(needs_root), decision, ",".join(targets), blocked_reason),
        )
        await db.commit()
    return cid


async def command_done(
    cmd_id: str,
    exit_code: int | None,
    duration_ms: int,
    stdout_hash: str,
    stderr_hash: str,
    approved_by: str | None = None,
) -> None:
    async with _db() as db:
        await db.execute(
            """UPDATE commands
               SET exit_code=?, duration_ms=?, stdout_hash=?, stderr_hash=?, approved_by=?
               WHERE id=?""",
            (exit_code, duration_ms, stdout_hash, stderr_hash, approved_by, cmd_id),
        )
        await db.commit()


async def output_append(cmd_id: str, stream: str, data: str) -> None:
    if not _STORE_OUTPUT:
        return
    compressed = gzip.compress(data.encode())
    async with _db() as db:
        await db.execute(
            "INSERT INTO outputs (cmd_id, stream, data) VALUES (?, ?, ?)",
            (cmd_id, stream, compressed),
        )
        await db.commit()


async def sessions_list() -> list[dict]:
    async with _db() as db:
        cur = await db.execute("SELECT * FROM sessions ORDER BY started_at DESC")
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def commands_list(session_id: str) -> list[dict]:
    async with _db() as db:
        cur = await db.execute(
            "SELECT * FROM commands WHERE session_id=? ORDER BY ts ASC",
            (session_id,),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


def _now() -> str:
    return datetime.now(UTC).isoformat()
