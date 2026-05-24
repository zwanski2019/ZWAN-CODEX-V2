"""
ReAct planner: Anthropic (claude-sonnet-4-6) → OpenRouter free → Ollama fallback.
Emits one JSON action per turn. Never constructs prompts that include credentials.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from agent.policy import Tier
from agent.registry import REGISTRY, browser_help_block, tool_registry_summary
from agent.scope import Scope

_MODEL = "claude-sonnet-4-6"
_MAX_ITERS = int(os.environ.get("ZWAN_MAX_ITERS", "25"))
_SESSION_BUDGET_SEC = int(os.environ.get("ZWAN_SESSION_BUDGET_SEC", "1800"))

_SYSTEM_PROMPT = """\
You are an autonomous offensive-security operator running on a Kali Linux system.
Your job is to plan the next single recon or exploitation action toward the stated goal.

CONSTRAINTS:
- You have NO access to credentials, passwords, or secrets. Do not ask for them.
- You may only use tools from the provided registry. Do not invent tool names.
- For privileged operations, set needs_root=true — the system handles auth out of band.
- If a tool is not in the registry, use "raw" (always requires explicit user approval).
- When unsure whether an action is safe, default tier to "exploit".
- When done with the goal or stuck, set "done": true.

RESPONSE FORMAT (strict JSON, no markdown fences, no extra keys):
{{
  "thought": "<your reasoning>",
  "tool": "<tool name from registry>",
  "args": {{"<slot>": "<value>", ...}},
  "needs_root": false,
  "tier": "recon",
  "rationale": "<one line: why this action now>",
  "done": false
}}

AVAILABLE TOOLS:
{tools}

BROWSER TOOL (stateful, DOM-driven):
{browser_help}

SCOPE (targets you are authorized to test):
{scope}
"""


@dataclass
class PlannerAction:
    thought: str
    tool: str
    args: dict
    needs_root: bool
    tier: Tier
    rationale: str
    done: bool
    action: dict | None = None     # populated for stateful tools (e.g. browser)


@dataclass
class Planner:
    scope: Scope
    goal: str
    history: list[dict] = field(default_factory=list)
    _iter: int = 0
    _started_at: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self._started_at = time.monotonic()

    @property
    def iters_left(self) -> int:
        return _MAX_ITERS - self._iter

    @property
    def budget_left_sec(self) -> float:
        return _SESSION_BUDGET_SEC - (time.monotonic() - self._started_at)

    def caps_hit(self) -> bool:
        return self._iter >= _MAX_ITERS or self.budget_left_sec <= 0

    async def next_action(self) -> PlannerAction:
        self._iter += 1
        system = _SYSTEM_PROMPT.format(
            tools=tool_registry_summary(),
            browser_help=browser_help_block(),
            scope=self._scope_summary(),
        )
        # Opening user message carries the goal; history then alternates
        # assistant→user (feed_result/feed_rejection), so no consecutive roles.
        opening = {"role": "user", "content": f"Goal: {self.goal}\n\nWhat is the next action?"}
        messages = [opening, *self.history]
        raw = await self._call_llm(system, messages)
        action = _parse_action(raw)
        self.history.append({"role": "assistant", "content": raw})
        return action

    def feed_result(self, tool: str, exit_code: int | None, stdout_preview: str, stderr_preview: str) -> None:
        result = {
            "tool": tool,
            "exit_code": exit_code,
            "stdout": stdout_preview[:2000],
            "stderr": stderr_preview[:500],
        }
        self.history.append({
            "role": "user",
            "content": f"Command result:\n{json.dumps(result, indent=2)}",
        })

    def feed_rejection(self, tool: str, reason: str) -> None:
        self.history.append({
            "role": "user",
            "content": f"Command '{tool}' was rejected: {reason}. Try a different approach.",
        })

    def _scope_summary(self) -> str:
        parts = []
        if self.scope.domains:
            parts.append("Domains: " + ", ".join(self.scope.domains))
        if self.scope.nets:
            parts.append("IPs: " + ", ".join(str(n) for n in self.scope.nets))
        if self.scope.out_domains:
            parts.append("Out-of-scope domains: " + ", ".join(self.scope.out_domains))
        if self.scope.out_nets:
            parts.append("Out-of-scope IPs: " + ", ".join(str(n) for n in self.scope.out_nets))
        return "\n".join(parts) if parts else "No scope loaded."

    async def _call_llm(self, system: str, messages: list[dict]) -> str:
        errors: list[str] = []

        try:
            return await _anthropic_call(system, messages)
        except Exception as e:
            errors.append(f"Anthropic: {e}")

        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if openrouter_key:
            try:
                return await _openrouter_call(system, messages, openrouter_key)
            except Exception as e:
                errors.append(f"OpenRouter: {e}")

        ollama_host = os.environ.get("OLLAMA_HOST", "")
        if ollama_host:
            try:
                return await _ollama_call(system, messages, ollama_host)
            except Exception as e:
                errors.append(f"Ollama: {e}")

        raise RuntimeError("All LLM backends failed.\n" + "\n".join(errors))


async def _anthropic_call(system: str, messages: list[dict]) -> str:
    import anthropic  # lazy import
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = await client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    return resp.content[0].text


_OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)


async def _openrouter_call(system: str, messages: list[dict], api_key: str) -> str:
    import httpx
    payload = {
        "model": _OPENROUTER_MODEL,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, *messages],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/zwanski2019/ZWAN-CODEX-V2",
        "X-Title": "ZWAN-CODEX",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _ollama_call(system: str, messages: list[dict], host: str) -> str:
    import httpx
    full_messages = [{"role": "system", "content": system}, *messages]
    model = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
    async with httpx.AsyncClient(base_url=host, timeout=120.0) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "model": model,
                "messages": full_messages,
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def _parse_action(raw: str) -> PlannerAction:
    text = raw.strip()
    # Strip markdown fences if the model wraps anyway
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    # If prose surrounds the JSON, extract the first {...} block
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Planner returned non-JSON: {exc}\nRaw: {raw[:200]}") from exc
    tier_str = str(data.get("tier", "exploit")).lower()
    tier = Tier.RECON if tier_str == "recon" else Tier.EXPLOIT

    args = data.get("args", {})
    if isinstance(args, list):
        # Planner occasionally returns positional list — convert to dict
        tool = data.get("tool", "raw")
        tool_def = REGISTRY.get(tool)
        if tool_def:
            slots = [p[1:-1] for p in tool_def.template if p.startswith("{")]
            args = {slots[i]: v for i, v in enumerate(args) if i < len(slots)}
        else:
            args = {"cmd": " ".join(str(a) for a in args)}

    action_obj = data.get("action")
    if not isinstance(action_obj, dict):
        action_obj = None

    return PlannerAction(
        thought=str(data.get("thought", "")),
        tool=str(data.get("tool", "raw")),
        args=args,
        needs_root=bool(data.get("needs_root", False)),
        tier=tier,
        rationale=str(data.get("rationale", "")),
        done=bool(data.get("done", False)),
        action=action_obj,
    )
