"""
Privileged executor with privsep sudo model.

The sudo password NEVER enters:
  - any variable that persists beyond the sudo -A -v call
  - any log, prompt, or LLM context
  - any struct field in this module

Flow:
  1. warm() runs sudo -n true. If it returns 0, timestamp is already warm.
  2. Otherwise, sudo -A -v with SUDO_ASKPASS prompts on /dev/tty.
     The askpass helper reads the password from the terminal and pipes
     it directly to sudo — then exits. No retention.
  3. _keepalive_loop() runs sudo -n -v every 60s to keep the timestamp warm.
  4. Privileged commands run as: sudo -n <binary> <args>
  5. Non-privileged commands run directly.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import AsyncIterator, Callable, Awaitable

from agent.policy import ParsedCommand

_ASKPASS = str(Path(__file__).parent / "askpass.sh")
_KEEPALIVE_INTERVAL = 60   # seconds


class SudoSession:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._warm = False

    async def warm(self) -> bool:
        """Check / warm the sudo timestamp. Returns True when warm."""
        # Check if already warm
        probe = await asyncio.create_subprocess_exec(
            "sudo", "-n", "true",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if await probe.wait() == 0:
            self._warm = True
            return True

        # Not warm — invoke askpass helper on the controlling terminal
        env = {**os.environ, "SUDO_ASKPASS": _ASKPASS}
        auth = await asyncio.create_subprocess_exec(
            "sudo", "-A", "-v",
            env=env,
        )
        self._warm = await auth.wait() == 0
        return self._warm

    def start_keepalive(self) -> None:
        self._task = asyncio.create_task(self._keepalive())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._warm = False

    async def _keepalive(self) -> None:
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            if not self._warm:
                break
            kp = await asyncio.create_subprocess_exec(
                "sudo", "-n", "-v",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kp.wait()


class Executor:
    def __init__(self, max_concurrent: int = 10) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self.sudo = SudoSession()

    async def ensure_sudo(self) -> bool:
        """Warm sudo timestamp if not already warm. Returns True on success."""
        ok = await self.sudo.warm()
        if ok and self.sudo._task is None:
            self.sudo.start_keepalive()
        return ok

    async def run(
        self,
        cmd: ParsedCommand,
        on_output: Callable[[str, str], Awaitable[None]] | None = None,
        dry_run: bool = False,
    ) -> tuple[int | None, str, str]:
        """
        Execute cmd. Returns (exit_code, stdout_hash, stderr_hash).
        exit_code is None in dry_run mode.
        on_output(stream, chunk) is called for each stdout/stderr chunk.
        """
        if dry_run:
            return None, "", ""

        argv = self._build_argv(cmd)

        async with self._sem:
            t0 = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_buf: list[str] = []
            stderr_buf: list[str] = []

            async def drain(stream: asyncio.StreamReader, name: str) -> None:
                while True:
                    chunk = await stream.read(4096)
                    if not chunk:
                        break
                    text = chunk.decode(errors="replace")
                    (stdout_buf if name == "stdout" else stderr_buf).append(text)
                    if on_output:
                        await on_output(name, text)

            await asyncio.gather(drain(proc.stdout, "stdout"), drain(proc.stderr, "stderr"))
            exit_code = await proc.wait()

        stdout = "".join(stdout_buf)
        stderr = "".join(stderr_buf)
        return (
            exit_code,
            hashlib.sha256(stdout.encode()).hexdigest(),
            hashlib.sha256(stderr.encode()).hexdigest(),
        )

    def _build_argv(self, cmd: ParsedCommand) -> list[str]:
        if cmd.needs_root:
            return ["sudo", "-n", cmd.binary, *cmd.args]
        return [cmd.binary, *cmd.args]

    def shutdown(self) -> None:
        self.sudo.stop()
