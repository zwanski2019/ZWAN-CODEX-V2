import pytest
from agent.scope import Scope
from agent.policy import ParsedCommand, Mode, Tier, Decision, evaluate

S = Scope.from_dict({"in_scope": {"domains": ["*.lab.local"], "ips": ["10.10.0.0/24"]}})

def cmd(binary, targets, **kw):
    return ParsedCommand(binary=binary, args=list(targets), targets=list(targets), **kw)

@pytest.mark.parametrize("mode", [Mode.MANUAL, Mode.AUTO, Mode.YOLO])
def test_out_of_scope_blocked_every_mode(mode):
    c = cmd("nuclei", ["evil.example.com"], tier=Tier.RECON)
    assert evaluate(c, mode, S) is Decision.BLOCK

def test_root_must_be_allowlisted():
    assert evaluate(cmd("ettercap", ["10.10.0.5"], needs_root=True), Mode.YOLO, S) is Decision.BLOCK
    assert evaluate(cmd("nmap", ["10.10.0.5"], needs_root=True, tier=Tier.RECON), Mode.YOLO, S) is Decision.ALLOW_AUTO

def test_recon_autoruns_in_auto():
    assert evaluate(cmd("httpx", ["api.lab.local"], tier=Tier.RECON), Mode.AUTO, S) is Decision.ALLOW_AUTO

def test_exploit_staged_in_auto_but_auto_in_yolo():
    c = cmd("sqlmap", ["api.lab.local"], tier=Tier.EXPLOIT)
    assert evaluate(c, Mode.AUTO, S) is Decision.NEEDS_APPROVAL
    assert evaluate(c, Mode.YOLO, S) is Decision.ALLOW_AUTO

def test_system_destructive_never_auto():
    c = cmd("rm", ["api.lab.local"], tier=Tier.RECON)   # in scope, but rm hits local box
    assert evaluate(c, Mode.YOLO, S) is Decision.NEEDS_APPROVAL

def test_unknown_tier_defaults_to_exploit():
    assert ParsedCommand(binary="x").tier is Tier.EXPLOIT
