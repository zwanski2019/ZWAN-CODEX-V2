from agent.scope import Scope

S = Scope.from_dict({
    "in_scope": {"domains": ["*.lab.local", "box.lab.local"], "ips": ["10.10.0.0/24"]},
    "out_of_scope": {"domains": ["admin.lab.local"], "ips": ["10.10.0.5/32"]},
})

def test_wildcard_and_apex():
    assert S.contains("api.lab.local")
    assert S.contains("lab.local")
    assert S.contains("https://api.lab.local:8443/x")

def test_out_of_scope_overrides_wildcard():
    assert not S.contains("admin.lab.local")

def test_cidr_membership():
    assert S.contains("10.10.0.20")
    assert not S.contains("10.10.0.5")     # carved out
    assert not S.contains("10.10.1.1")     # outside /24

def test_unknown_is_denied():
    assert not S.contains("evil.example.com")
    assert not S.contains("")
