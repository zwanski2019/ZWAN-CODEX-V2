"""
Browser-tool policy tests — pure policy, no Playwright runtime needed.
Mirrors test_policy.py shape: tiny ParsedCommand factories, exhaustive over modes + scope cases.
"""
from __future__ import annotations

from agent.policy import Decision, Mode, ParsedCommand, Tier, evaluate
from agent.registry import browser_action_tier
from agent.scope import Scope


SCOPE = Scope.from_dict({"in_scope": {"domains": ["*.lab.local"]}})


def _b(op: str, host: str, tier: Tier) -> ParsedCommand:
    return ParsedCommand(binary="browser", args=[op], targets=[host], tier=tier)


# ── tier_map sanity ─────────────────────────────────────────────────────────

def test_recon_ops_are_recon():
    for op in ("goto", "back", "extract", "screenshot"):
        assert browser_action_tier(op) is Tier.RECON, op


def test_state_change_ops_are_exploit():
    for op in ("click", "type", "submit"):
        assert browser_action_tier(op) is Tier.EXPLOIT, op


def test_unknown_op_fails_closed():
    assert browser_action_tier("teleport") is Tier.EXPLOIT


# ── scope gate ──────────────────────────────────────────────────────────────

def test_goto_out_of_scope_blocked_yolo():
    cmd = _b("goto", "evil.example.com", Tier.RECON)
    assert evaluate(cmd, Mode.YOLO, SCOPE, dry_run=False) is Decision.BLOCK


def test_goto_out_of_scope_blocked_manual():
    cmd = _b("goto", "evil.example.com", Tier.RECON)
    assert evaluate(cmd, Mode.MANUAL, SCOPE, dry_run=False) is Decision.BLOCK


def test_goto_in_scope_auto_recon_autoruns():
    cmd = _b("goto", "app.lab.local", Tier.RECON)
    assert evaluate(cmd, Mode.AUTO, SCOPE, dry_run=False) is Decision.ALLOW_AUTO


def test_extract_in_scope_auto_recon_autoruns():
    cmd = _b("extract", "app.lab.local", Tier.RECON)
    assert evaluate(cmd, Mode.AUTO, SCOPE, dry_run=False) is Decision.ALLOW_AUTO


# ── exploit gating in AUTO ──────────────────────────────────────────────────

def test_form_submit_staged_in_auto():
    cmd = _b("submit", "app.lab.local", Tier.EXPLOIT)
    assert evaluate(cmd, Mode.AUTO, SCOPE, dry_run=False) is Decision.NEEDS_APPROVAL


def test_type_staged_in_auto():
    cmd = _b("type", "app.lab.local", Tier.EXPLOIT)
    assert evaluate(cmd, Mode.AUTO, SCOPE, dry_run=False) is Decision.NEEDS_APPROVAL


def test_click_autoruns_in_yolo():
    cmd = _b("click", "app.lab.local", Tier.EXPLOIT)
    assert evaluate(cmd, Mode.YOLO, SCOPE, dry_run=False) is Decision.ALLOW_AUTO


# ── MANUAL always gates everything (browser is not exempt) ──────────────────

def test_manual_stages_even_recon_browser():
    cmd = _b("goto", "app.lab.local", Tier.RECON)
    assert evaluate(cmd, Mode.MANUAL, SCOPE, dry_run=False) is Decision.NEEDS_APPROVAL


# ── multi-target (action URL + current page URL) ────────────────────────────

def test_multi_target_one_out_of_scope_blocks():
    """Browser builds targets = [action_url_host, current_page_host]. Both must be in scope."""
    cmd = ParsedCommand(
        binary="browser",
        args=["goto"],
        targets=["app.lab.local", "evil.example.com"],
        tier=Tier.RECON,
    )
    assert evaluate(cmd, Mode.YOLO, SCOPE, dry_run=False) is Decision.BLOCK
