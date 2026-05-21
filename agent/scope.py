from __future__ import annotations
import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urlparse
import yaml


def _host_of(target: str) -> str:
    t = target.strip().lower()
    if "://" in t:
        t = urlparse(t).hostname or t
    # strip port
    if t.count(":") == 1 and not _is_ip(t):
        t = t.split(":", 1)[0]
    return t.rstrip(".")


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _domain_matches(host: str, pattern: str) -> bool:
    pattern = pattern.lower().rstrip(".")
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return host == suffix or host.endswith("." + suffix)
    return host == pattern


@dataclass
class Scope:
    domains: list[str] = field(default_factory=list)
    nets: list[ipaddress._BaseNetwork] = field(default_factory=list)
    out_domains: list[str] = field(default_factory=list)
    out_nets: list[ipaddress._BaseNetwork] = field(default_factory=list)

    @classmethod
    def load(cls, path: str) -> "Scope":
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Scope":
        def nets(items): return [ipaddress.ip_network(x, strict=False) for x in items]
        ins, outs = data.get("in_scope", {}), data.get("out_of_scope", {})
        return cls(
            domains=[d.lower() for d in ins.get("domains", [])],
            nets=nets(ins.get("ips", [])),
            out_domains=[d.lower() for d in outs.get("domains", [])],
            out_nets=nets(outs.get("ips", [])),
        )

    def contains(self, target: str) -> bool:
        """Default-deny. out_of_scope always wins over in_scope."""
        host = _host_of(target)
        if not host:
            return False
        if _is_ip(host):
            ip = ipaddress.ip_address(host)
            if any(ip in n for n in self.out_nets):
                return False
            return any(ip in n for n in self.nets)
        # domain
        if any(_domain_matches(host, p) for p in self.out_domains):
            return False
        return any(_domain_matches(host, p) for p in self.domains)
