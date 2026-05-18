"""Async subprocess helper used by all tool wrappers."""
from __future__ import annotations

import asyncio
import json
import shlex


async def run(cmd: str, timeout: int = 300) -> tuple[str, str, int]:
    """Run shell command, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return "", f"timeout after {timeout}s", -1
    return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode


async def run_json(cmd: str, timeout: int = 300) -> list[dict]:
    """Run command that outputs newline-delimited JSON, parse and return list."""
    stdout, _, _ = await run(cmd, timeout=timeout)
    results = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return results
