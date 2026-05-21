"""
Planner unit tests — no network, no Anthropic API.
Stubs _call_llm to return canned JSON and verifies message structure,
action parsing, history management, and error handling.
"""
from __future__ import annotations

import json
import pytest

from agent.planner import Planner, _parse_action
from agent.policy import Tier
from agent.scope import Scope


SCOPE = Scope.from_dict({"in_scope": {"domains": ["*.lab.local"]}})

_VALID_ACTION = json.dumps({
    "thought": "Start with subdomain enum",
    "tool": "subfinder",
    "args": {"domain": "lab.local"},
    "needs_root": False,
    "tier": "recon",
    "rationale": "discover attack surface",
    "done": False,
})

_DONE_ACTION = json.dumps({
    "thought": "Nothing left to do",
    "tool": "subfinder",
    "args": {},
    "needs_root": False,
    "tier": "recon",
    "rationale": "goal reached",
    "done": True,
})


def _stub_planner(goal: str = "recon lab.local") -> Planner:
    return Planner(scope=SCOPE, goal=goal)


# ── _parse_action ─────────────────────────────────────────────────────────────

def test_parse_valid_action():
    a = _parse_action(_VALID_ACTION)
    assert a.tool == "subfinder"
    assert a.args == {"domain": "lab.local"}
    assert a.tier is Tier.RECON
    assert not a.done


def test_parse_done_flag():
    a = _parse_action(_DONE_ACTION)
    assert a.done


def test_parse_strips_markdown_fences():
    fenced = f"```json\n{_VALID_ACTION}\n```"
    a = _parse_action(fenced)
    assert a.tool == "subfinder"


def test_parse_extracts_json_from_prose():
    prose = f"Here is my analysis:\n{_VALID_ACTION}\nDone."
    a = _parse_action(prose)
    assert a.tool == "subfinder"


def test_parse_raises_on_garbage():
    with pytest.raises(ValueError, match="non-JSON"):
        _parse_action("no json here at all")


def test_parse_positional_args_list():
    """Planner sometimes returns args as a positional list — should convert to dict."""
    raw = json.dumps({
        "thought": "t", "tool": "subfinder",
        "args": ["lab.local"],
        "needs_root": False, "tier": "recon", "rationale": "r", "done": False,
    })
    a = _parse_action(raw)
    assert a.args.get("domain") == "lab.local"


def test_parse_unknown_tier_defaults_to_exploit():
    raw = json.dumps({
        "thought": "t", "tool": "subfinder", "args": {},
        "needs_root": False, "tier": "nuclear", "rationale": "r", "done": False,
    })
    a = _parse_action(raw)
    assert a.tier is Tier.EXPLOIT


# ── message structure ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_first_call_no_consecutive_user_messages(monkeypatch):
    """On iteration 1 (empty history), messages must not have consecutive user roles."""
    captured: list[list[dict]] = []

    async def fake_call(system, messages):
        captured.append(list(messages))
        return _VALID_ACTION

    p = _stub_planner()
    monkeypatch.setattr("agent.planner._anthropic_call", fake_call)
    await p.next_action()

    msgs = captured[0]
    for i in range(len(msgs) - 1):
        assert msgs[i]["role"] != msgs[i + 1]["role"], (
            f"Consecutive '{msgs[i]['role']}' messages at positions {i},{i+1}"
        )


@pytest.mark.asyncio
async def test_second_call_no_consecutive_user_messages(monkeypatch):
    """After feed_result, the next call must still have alternating roles."""
    async def fake_call(system, messages):
        return _VALID_ACTION

    p = _stub_planner()
    monkeypatch.setattr("agent.planner._anthropic_call", fake_call)

    action = await p.next_action()
    p.feed_result(action.tool, 0, "sub1.lab.local", "")

    captured: list[list[dict]] = []

    async def capture_call(system, messages):
        captured.append(list(messages))
        return _VALID_ACTION

    monkeypatch.setattr("agent.planner._anthropic_call", capture_call)
    await p.next_action()

    msgs = captured[0]
    for i in range(len(msgs) - 1):
        assert msgs[i]["role"] != msgs[i + 1]["role"], (
            f"Consecutive '{msgs[i]['role']}' messages at positions {i},{i+1}"
        )


# ── caps & budget ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_caps_hit_after_max_iters(monkeypatch):
    import agent.planner as pl_mod
    monkeypatch.setattr(pl_mod, "_MAX_ITERS", 2)

    async def fake_call(system, messages):
        return _VALID_ACTION

    p = _stub_planner()
    monkeypatch.setattr("agent.planner._anthropic_call", fake_call)

    assert not p.caps_hit()
    await p.next_action()
    await p.next_action()
    assert p.caps_hit()


# ── feed_rejection ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_feed_rejection_appends_user_message(monkeypatch):
    async def fake_call(system, messages):
        return _VALID_ACTION

    p = _stub_planner()
    monkeypatch.setattr("agent.planner._anthropic_call", fake_call)
    await p.next_action()  # appends assistant message

    p.feed_rejection("subfinder", "out of scope")

    # Last history entry must be a user message
    assert p.history[-1]["role"] == "user"
    assert "rejected" in p.history[-1]["content"]
