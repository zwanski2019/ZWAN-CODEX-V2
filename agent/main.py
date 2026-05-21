"""
ZWAN-AGENT daemon — FastAPI + WebSocket, 127.0.0.1 only, token auth.

Token is generated at startup, printed once to stdout.
The React frontend sends it in the first `auth` WS frame.
Credentials never enter LLM context.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import time
import uuid
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent import audit
from agent.executor import Executor
from agent.planner import Planner, PlannerAction
from agent.policy import Decision, Mode, ParsedCommand, Tier, evaluate
from agent.registry import (
    BROWSER_ACTIONS,
    REGISTRY,
    STATEFUL_TOOLS,
    browser_action_tier,
    extract_targets,
    render,
)
from agent.scope import Scope
from agent.tools.browser import Browser
from agent.tools import caido as caido_mod

_CAIDO_TOOLS: set[str] = {"caido_history", "caido_create_finding"}


class ScopeViolation(Exception):
    """Raised when a live browser navigation lands off-scope mid-session."""

_PORT = int(os.environ.get("ZWAN_AGENT_PORT", "8788"))
_HOST = "127.0.0.1"

TOKEN = secrets.token_hex(32)

app = FastAPI(title="zwan-agent", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Active session state ───────────────────────────────────────────────────────

class AgentSession:
    def __init__(self, goal: str, mode: Mode, scope: Scope, scope_hash: str,
                 dry_run: bool, ws: WebSocket) -> None:
        self.goal = goal
        self.mode = mode
        self.scope = scope
        self.scope_hash = scope_hash
        self.dry_run = dry_run
        self.ws = ws
        self.session_id: str | None = None
        self._approval: asyncio.Future[bool] | None = None
        self._task: asyncio.Task | None = None
        self._executor = Executor(max_concurrent=10)
        self._browser: Browser | None = None
        self._stdout_buf: dict[str, list[str]] = {}
        self._stderr_buf: dict[str, list[str]] = {}

    async def start(self) -> None:
        self.session_id = await audit.session_open(
            self.goal, self.mode.value, self.scope_hash
        )
        self._task = asyncio.create_task(self._run_loop())

    def abort(self) -> None:
        if self._approval and not self._approval.done():
            self._approval.cancel()
        if self._task and not self._task.done():
            self._task.cancel()
        self._executor.shutdown()

    def approve(self, cmd_id: str) -> None:
        if self._approval and not self._approval.done():
            self._approval.set_result(True)

    def reject(self, cmd_id: str) -> None:
        if self._approval and not self._approval.done():
            self._approval.set_result(False)

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode

    def set_dry_run(self, flag: bool) -> None:
        self.dry_run = flag

    async def _send(self, msg: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(msg))
        except Exception:
            pass

    async def _run_loop(self) -> None:
        planner = Planner(scope=self.scope, goal=self.goal)
        findings: list[str] = []

        await self._send({"type": "thought", "text": f"Starting session. Goal: {self.goal}"})
        await self._send({
            "type": "budget",
            "iters_left": planner.iters_left,
            "budget_left_sec": round(planner.budget_left_sec),
        })

        try:
            while not planner.caps_hit():
                # Ask planner for next action
                try:
                    action = await planner.next_action()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._send({"type": "error", "message": f"Planner error: {exc}"})
                    break

                await self._send({"type": "thought", "text": action.thought})
                await self._send({
                    "type": "budget",
                    "iters_left": planner.iters_left,
                    "budget_left_sec": round(planner.budget_left_sec),
                })

                if action.done:
                    break

                # Validate tool exists
                if action.tool not in REGISTRY:
                    await self._send({
                        "type": "error",
                        "message": f"Unknown tool '{action.tool}' — planner must use registered tools only.",
                    })
                    planner.feed_rejection(action.tool, "tool not in registry")
                    continue

                # Stateful tools take a separate path (bypass executor).
                if action.tool in STATEFUL_TOOLS:
                    if action.tool in _CAIDO_TOOLS:
                        await self._handle_caido_turn(planner, action)
                    else:
                        try:
                            await self._handle_browser_turn(planner, action)
                        except ScopeViolation as exc:
                            await self._send({
                                "type": "error",
                                "message": f"Scope violation: live page redirected to '{exc}'. Session halted.",
                            })
                            break
                    continue

                # Render command from registry template
                try:
                    binary, argv = render(action.tool, action.args)
                except Exception as exc:
                    await self._send({"type": "error", "message": f"Render error: {exc}"})
                    planner.feed_rejection(action.tool, str(exc))
                    continue

                tool_def = REGISTRY[action.tool]
                targets = extract_targets(action.tool, action.args)
                needs_root = action.needs_root or tool_def.needs_root_default
                tier = action.tier if action.tool != "raw" else Tier.EXPLOIT

                parsed = ParsedCommand(
                    binary=binary,
                    args=argv,
                    targets=targets,
                    needs_root=needs_root,
                    tier=tier,
                )
                rendered_cmd = ("sudo -n " if needs_root else "") + parsed.rendered

                # Policy evaluation (raw tool always forced to NEEDS_APPROVAL)
                if action.tool == "raw":
                    decision = Decision.NEEDS_APPROVAL
                    blocked_reason = None
                else:
                    decision = evaluate(parsed, self.mode, self.scope, self.dry_run)
                    blocked_reason = None

                cmd_id = str(uuid.uuid4())
                audit_id = await audit.command_log(
                    session_id=self.session_id,
                    tool=action.tool,
                    rendered_cmd=rendered_cmd,
                    tier=tier.value,
                    needs_root=needs_root,
                    decision=decision.value,
                    targets=targets,
                    blocked_reason=_block_reason(parsed, self.mode, self.scope) if decision is Decision.BLOCK else None,
                )

                await self._send({
                    "type": "command_proposed",
                    "cmd_id": cmd_id,
                    "audit_id": audit_id,
                    "tool": action.tool,
                    "rendered": rendered_cmd,
                    "tier": tier.value,
                    "targets": targets,
                    "needs_root": needs_root,
                    "decision": decision.value,
                    "rationale": action.rationale,
                    "dry_run": self.dry_run,
                })

                if decision is Decision.BLOCK:
                    reason = _block_reason(parsed, self.mode, self.scope)
                    await self._send({"type": "blocked", "cmd_id": cmd_id, "reason": reason})
                    planner.feed_rejection(action.tool, reason)
                    continue

                approved_by: str | None = None
                if decision is Decision.NEEDS_APPROVAL:
                    await self._send({"type": "awaiting_approval", "cmd_id": cmd_id})
                    self._approval = asyncio.get_event_loop().create_future()
                    try:
                        approved = await asyncio.wait_for(self._approval, timeout=300.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        await self._send({"type": "error", "message": "Approval timed out or session aborted."})
                        break
                    finally:
                        self._approval = None

                    if not approved:
                        planner.feed_rejection(action.tool, "rejected by operator")
                        continue
                    approved_by = "operator"

                # Handle sudo warm-up before elevated execution
                if needs_root and not self.dry_run:
                    warm = await self._executor.ensure_sudo()
                    if not warm:
                        await self._send({"type": "sudo_prompt_required", "cmd_id": cmd_id})
                        await self._send({
                            "type": "error",
                            "message": "sudo authentication failed — run 'sudo -v' in the terminal running the agent.",
                        })
                        planner.feed_rejection(action.tool, "sudo auth failed")
                        continue

                # Execute
                t0 = time.monotonic()
                stdout_chunks: list[str] = []
                stderr_chunks: list[str] = []

                async def on_output(stream: str, data: str) -> None:
                    (stdout_chunks if stream == "stdout" else stderr_chunks).append(data)
                    await self._send({"type": "output_chunk", "cmd_id": cmd_id, "stream": stream, "data": data})
                    await audit.output_append(audit_id, stream, data)

                exit_code, stdout_hash, stderr_hash = await self._executor.run(
                    parsed, on_output=on_output, dry_run=self.dry_run
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

                await audit.command_done(
                    audit_id, exit_code, duration_ms,
                    stdout_hash, stderr_hash, approved_by
                )
                await self._send({
                    "type": "command_done",
                    "cmd_id": cmd_id,
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    "dry_run": self.dry_run,
                })

                planner.feed_result(
                    action.tool, exit_code,
                    "".join(stdout_chunks),
                    "".join(stderr_chunks),
                )

            summary = f"Session complete. Iterations: {planner._iter}/{25}."
            if planner.caps_hit():
                summary += " Cap reached."

        except asyncio.CancelledError:
            summary = "Session aborted by operator."
        except Exception as exc:
            summary = f"Session error: {exc}"
            await self._send({"type": "error", "message": str(exc)})
        finally:
            self._executor.shutdown()
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self.session_id:
                await audit.session_close(self.session_id, summary)
            await self._send({"type": "session_done", "summary": summary})

    # ── Stateful: browser ────────────────────────────────────────────────────

    async def _handle_browser_turn(self, planner: Planner, action: PlannerAction) -> None:
        """Browser action turn: same policy/approval gates as CLI tools,
        plus a post-action scope re-check that hard-stops on out-of-scope redirects."""
        act = action.action or {}
        op = str(act.get("op", ""))

        if op not in BROWSER_ACTIONS:
            await self._send({
                "type": "error",
                "message": f"Invalid browser op '{op}' — allowed: {sorted(BROWSER_ACTIONS)}",
            })
            planner.feed_rejection("browser", f"invalid op {op!r}")
            return

        # Build targets: action URL (for goto) + current page URL (always, if known).
        targets: list[str] = []
        if op == "goto":
            url = str(act.get("url", "")).strip()
            if not url:
                planner.feed_rejection("browser", "goto requires url")
                await self._send({"type": "error", "message": "browser.goto requires 'url'"})
                return
            targets.append(url)
        if self._browser and self._browser.current_url:
            targets.append(self._browser.current_url)

        # Tier: action default; planner may upgrade to EXPLOIT (e.g. typing a password).
        tier = browser_action_tier(op)
        if action.tier is Tier.EXPLOIT:
            tier = Tier.EXPLOIT

        rendered_cmd = _render_browser_action(op, act)

        parsed = ParsedCommand(
            binary="browser",
            args=[op],
            targets=targets,
            needs_root=False,
            tier=tier,
        )

        decision = evaluate(parsed, self.mode, self.scope, self.dry_run)

        cmd_id = str(uuid.uuid4())
        audit_id = await audit.command_log(
            session_id=self.session_id,
            tool="browser",
            rendered_cmd=rendered_cmd,
            tier=tier.value,
            needs_root=False,
            decision=decision.value,
            targets=targets,
            blocked_reason=_block_reason(parsed, self.mode, self.scope) if decision is Decision.BLOCK else None,
        )

        await self._send({
            "type": "command_proposed",
            "cmd_id": cmd_id,
            "audit_id": audit_id,
            "tool": "browser",
            "rendered": rendered_cmd,
            "tier": tier.value,
            "targets": targets,
            "needs_root": False,
            "decision": decision.value,
            "rationale": action.rationale,
            "dry_run": self.dry_run,
        })

        if decision is Decision.BLOCK:
            reason = _block_reason(parsed, self.mode, self.scope)
            await self._send({"type": "blocked", "cmd_id": cmd_id, "reason": reason})
            planner.feed_rejection("browser", reason)
            return

        approved_by: str | None = None
        if decision is Decision.NEEDS_APPROVAL:
            await self._send({"type": "awaiting_approval", "cmd_id": cmd_id})
            self._approval = asyncio.get_event_loop().create_future()
            try:
                approved = await asyncio.wait_for(self._approval, timeout=300.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                await self._send({"type": "error", "message": "Approval timed out or session aborted."})
                raise
            finally:
                self._approval = None
            if not approved:
                planner.feed_rejection("browser", "rejected by operator")
                return
            approved_by = "operator"

        # Execute (or stub in dry-run).
        t0 = time.monotonic()
        exit_code: int | None
        stdout_text = ""
        stderr_text = ""

        if self.dry_run:
            exit_code = None
            stdout_text = f"(dry-run) would {rendered_cmd}"
        else:
            try:
                if self._browser is None:
                    self._browser = Browser(headless=True)
                    await self._browser.start()
                stdout_text = await self._browser.act(act)
                exit_code = 0
            except Exception as exc:
                exit_code = 1
                stderr_text = f"{type(exc).__name__}: {exc}"

            # Post-action scope re-check — hard-stop on out-of-scope navigation.
            host = self._browser.current_host() if self._browser else ""
            if host and not self.scope.contains(host):
                try:
                    await self._browser._page.go_back()
                except Exception:
                    pass
                await self._send({
                    "type": "blocked",
                    "cmd_id": cmd_id,
                    "reason": f"browser_redirect_out_of_scope: {host}",
                })
                raise ScopeViolation(host)

            # Live frame for the Console viewer — emit before observe so the user sees
            # the page state even if observe() fails on a weird DOM.
            frame_b64 = await self._browser.snap()
            if frame_b64:
                await self._send({
                    "type": "browser_frame",
                    "cmd_id": cmd_id,
                    "url": self._browser.current_url,
                    "png_b64": frame_b64,
                })

            # Feed the new DOM observation + discovered endpoints back to the planner.
            try:
                obs = await self._browser.observe()
                endpoints = self._browser.discovered()
                browser_state = json.dumps({
                    "url": self._browser.current_url,
                    "elements": obs,
                    "discovered_endpoints": endpoints[-30:],
                })
                stdout_text = (stdout_text + "\n\n" if stdout_text else "") + "BROWSER_STATE: " + browser_state
                await self._send({
                    "type": "browser_state",
                    "cmd_id": cmd_id,
                    "url": self._browser.current_url,
                    "elements": obs,
                    "discovered": endpoints,
                })
            except Exception as exc:
                stderr_text = (stderr_text + " | " if stderr_text else "") + f"observe failed: {exc}"

        # Stream stdout/stderr as one chunk each (browser results aren't a long stream).
        if stdout_text:
            await self._send({"type": "output_chunk", "cmd_id": cmd_id, "stream": "stdout", "data": stdout_text})
            await audit.output_append(audit_id, "stdout", stdout_text)
        if stderr_text:
            await self._send({"type": "output_chunk", "cmd_id": cmd_id, "stream": "stderr", "data": stderr_text})
            await audit.output_append(audit_id, "stderr", stderr_text)

        duration_ms = int((time.monotonic() - t0) * 1000)
        stdout_hash = hashlib.sha256(stdout_text.encode()).hexdigest()
        stderr_hash = hashlib.sha256(stderr_text.encode()).hexdigest()
        await audit.command_done(audit_id, exit_code, duration_ms, stdout_hash, stderr_hash, approved_by)
        await self._send({
            "type": "command_done",
            "cmd_id": cmd_id,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "dry_run": self.dry_run,
        })

        planner.feed_result("browser", exit_code, stdout_text, stderr_text)

    # ── Stateful: Caido ──────────────────────────────────────────────────────

    async def _handle_caido_turn(self, planner: Planner, action: PlannerAction) -> None:
        """Caido API tool turn: policy gates, then call Caido GraphQL."""
        tool = action.tool
        args = action.args or {}

        # Determine targets for scope check
        host = str(args.get("host", "") or args.get("host_filter", ""))
        targets: list[str] = [host] if host else []
        tier = Tier.RECON if tool == "caido_history" else Tier.EXPLOIT

        slots = ", ".join(f"{k}={v!r}" for k, v in args.items() if k != "description")
        rendered_cmd = f"caido.{tool}({slots})"

        parsed = ParsedCommand(binary="caido", args=[tool], targets=targets,
                               needs_root=False, tier=tier)
        decision = evaluate(parsed, self.mode, self.scope, self.dry_run)

        cmd_id = str(uuid.uuid4())
        audit_id = await audit.command_log(
            session_id=self.session_id,
            tool=tool,
            rendered_cmd=rendered_cmd,
            tier=tier.value,
            needs_root=False,
            decision=decision.value,
            targets=targets,
            blocked_reason=_block_reason(parsed, self.mode, self.scope) if decision is Decision.BLOCK else None,
        )
        await self._send({
            "type": "command_proposed",
            "cmd_id": cmd_id,
            "audit_id": audit_id,
            "tool": tool,
            "rendered": rendered_cmd,
            "tier": tier.value,
            "targets": targets,
            "needs_root": False,
            "decision": decision.value,
            "rationale": action.rationale,
            "dry_run": self.dry_run,
        })

        if decision is Decision.BLOCK:
            reason = _block_reason(parsed, self.mode, self.scope)
            await self._send({"type": "blocked", "cmd_id": cmd_id, "reason": reason})
            planner.feed_rejection(tool, reason)
            return

        approved_by: str | None = None
        if decision is Decision.NEEDS_APPROVAL:
            await self._send({"type": "awaiting_approval", "cmd_id": cmd_id})
            self._approval = asyncio.get_event_loop().create_future()
            try:
                approved = await asyncio.wait_for(self._approval, timeout=300.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                await self._send({"type": "error", "message": "Approval timed out."})
                return
            finally:
                self._approval = None
            if not approved:
                planner.feed_rejection(tool, "rejected by operator")
                return
            approved_by = "operator"

        t0 = time.monotonic()
        stdout_text = stderr_text = ""
        exit_code: int | None = None

        if self.dry_run:
            stdout_text = f"(dry-run) would {rendered_cmd}"
        else:
            try:
                if tool == "caido_history":
                    limit = int(args.get("limit", 50))
                    rows = await caido_mod.history(limit=limit, host_filter=host)
                    stdout_text = caido_mod.format_history_table(rows)
                    exit_code = 0
                elif tool == "caido_create_finding":
                    result = await caido_mod.create_finding(
                        request_id=str(args.get("request_id", "")),
                        title=str(args.get("title", "Untitled Finding")),
                        description=str(args.get("description", "")),
                    )
                    stdout_text = f"Finding created: {json.dumps(result, indent=2)}"
                    exit_code = 0
            except Exception as exc:
                stderr_text = f"{type(exc).__name__}: {exc}"
                exit_code = 1

        duration_ms = int((time.monotonic() - t0) * 1000)
        stdout_hash = hashlib.sha256(stdout_text.encode()).hexdigest()
        stderr_hash = hashlib.sha256(stderr_text.encode()).hexdigest()

        if stdout_text:
            await self._send({"type": "output_chunk", "cmd_id": cmd_id, "stream": "stdout", "data": stdout_text})
            await audit.output_append(audit_id, "stdout", stdout_text)
        if stderr_text:
            await self._send({"type": "output_chunk", "cmd_id": cmd_id, "stream": "stderr", "data": stderr_text})
            await audit.output_append(audit_id, "stderr", stderr_text)

        await audit.command_done(audit_id, exit_code, duration_ms, stdout_hash, stderr_hash, approved_by)
        await self._send({"type": "command_done", "cmd_id": cmd_id, "exit_code": exit_code,
                          "duration_ms": duration_ms, "dry_run": self.dry_run})
        planner.feed_result(tool, exit_code, stdout_text, stderr_text)


def _render_browser_action(op: str, act: dict) -> str:
    if op == "goto":
        return f"browser.goto({act.get('url', '')})"
    if op == "type":
        v = str(act.get("value", ""))
        v_disp = (v[:32] + "…") if len(v) > 32 else v
        return f"browser.type(id={act.get('id')}, value={v_disp!r})"
    if op in ("click", "submit"):
        return f"browser.{op}(id={act.get('id')})"
    return f"browser.{op}()"


def _block_reason(cmd: ParsedCommand, mode: Mode, scope: Scope) -> str:
    for t in cmd.targets:
        if not scope.contains(t):
            return f"out_of_scope: {t}"
    if cmd.needs_root and cmd.binary not in {"nmap", "masscan", "naabu", "tcpdump"}:
        return f"root_not_allowlisted: {cmd.binary}"
    return "policy_block"


# ── WebSocket endpoint ────────────────────────────────────────────────────────

_active_session: AgentSession | None = None


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    global _active_session
    await websocket.accept()

    # Step 1: auth
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        msg = json.loads(raw)
        if msg.get("type") != "auth" or msg.get("token") != TOKEN:
            await websocket.close(code=4001, reason="Unauthorized")
            return
        await websocket.send_text(json.dumps({"type": "auth_ok"}))
    except Exception:
        await websocket.close(code=4001, reason="Auth failed")
        return

    session: AgentSession | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            msg: dict = json.loads(raw)
            t = msg.get("type")

            if t == "start_session":
                if _active_session and _active_session._task and not _active_session._task.done():
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Another session is running. Abort it first.",
                    }))
                    continue

                scope_yaml = msg.get("scope", "")
                scope_data = yaml.safe_load(scope_yaml) if scope_yaml else {}
                scope = Scope.from_dict(scope_data or {})
                scope_hash = hashlib.sha256(scope_yaml.encode()).hexdigest()

                mode_str = str(msg.get("mode", "manual")).lower()
                mode = Mode(mode_str) if mode_str in {m.value for m in Mode} else Mode.MANUAL
                dry_run = bool(msg.get("dry_run", False))
                goal = str(msg.get("goal", ""))

                session = AgentSession(
                    goal=goal, mode=mode, scope=scope,
                    scope_hash=scope_hash, dry_run=dry_run, ws=websocket,
                )
                _active_session = session
                await session.start()

            elif t == "set_mode" and session:
                mode_str = str(msg.get("mode", "manual")).lower()
                mode = Mode(mode_str) if mode_str in {m.value for m in Mode} else Mode.MANUAL
                session.set_mode(mode)
                await websocket.send_text(json.dumps({"type": "mode_updated", "mode": mode.value}))

            elif t == "set_dry_run" and session:
                session.set_dry_run(bool(msg.get("value", False)))

            elif t == "approve" and session:
                session.approve(str(msg.get("cmd_id", "")))

            elif t == "reject" and session:
                session.reject(str(msg.get("cmd_id", "")))

            elif t == "abort" and session:
                session.abort()
                session = None
                _active_session = None

            elif t == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if session:
            session.abort()


# ── HTTP endpoints for the Audit tab ─────────────────────────────────────────

@app.get("/api/sessions")
async def list_sessions() -> list[dict]:
    return await audit.sessions_list()


@app.get("/api/sessions/{session_id}/commands")
async def list_commands(session_id: str) -> list[dict]:
    return await audit.commands_list(session_id)


@app.get("/api/sessions/{session_id}/export")
async def export_session(session_id: str) -> dict:
    session_rows = await audit.sessions_list()
    sess = next((s for s in session_rows if s["id"] == session_id), None)
    if not sess:
        return {"error": "not found"}
    cmds = await audit.commands_list(session_id)
    lines = [
        f"# Session: {sess.get('goal', 'unknown')}",
        f"Mode: {sess.get('mode')}  |  Started: {sess.get('started_at')}",
        f"Summary: {sess.get('summary', '')}",
        "",
        "## Commands",
    ]
    for c in cmds:
        status = f"exit={c['exit_code']}" if c["exit_code"] is not None else c["decision"]
        lines.append(f"- `{c['rendered_cmd']}` [{c['tier']}/{status}]")
    return {"markdown": "\n".join(lines)}


@app.get("/api/caido/status")
async def caido_status() -> dict:
    alive = await caido_mod.alive()
    return {
        "alive": alive,
        "url": caido_mod.CAIDO_URL,
        "has_key": bool(caido_mod._active_token()),
        "proxy": caido_mod.CAIDO_PROXY or None,
    }


@app.post("/api/caido/login")
async def caido_login() -> dict:
    """
    Start the Caido device-code auth flow.
    Returns the verificationUrl and userCode for the user to approve.
    A background task subscribes to the GQL WebSocket and caches the token when approved.
    """
    try:
        req = await caido_mod.start_device_flow()
    except Exception as exc:
        return {"error": str(exc)}

    request_id = req.get("id", "")
    if not request_id:
        return {"error": "Caido did not return a request ID"}

    async def _on_token(access: str, refresh: str) -> None:
        # Token is already stored in caido_mod._cached_token by wait_for_token
        pass

    asyncio.create_task(caido_mod.wait_for_token(request_id, _on_token))

    return {
        "requestId": request_id,
        "userCode": req.get("userCode"),
        "verificationUrl": req.get("verificationUrl"),
        "expiresAt": req.get("expiresAt"),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.1.0"}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Route all CLI subprocesses through Caido's intercept proxy when configured.
    # This makes every tool call (curl, httpx, nuclei, etc.) visible in Caido's history.
    if caido_proxy := caido_mod.CAIDO_PROXY:
        os.environ.setdefault("HTTP_PROXY", caido_proxy)
        os.environ.setdefault("HTTPS_PROXY", caido_proxy)
        print(f"[ZWAN-AGENT] Caido proxy: all CLI tools → {caido_proxy}", flush=True)

    print(f"\n[ZWAN-AGENT] Token: {TOKEN}\n", flush=True)
    print(f"[ZWAN-AGENT] Listening on {_HOST}:{_PORT}", flush=True)
    uvicorn.run(app, host=_HOST, port=_PORT, log_level="warning")


if __name__ == "__main__":
    main()
