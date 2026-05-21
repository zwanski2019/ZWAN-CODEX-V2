"""
Tool registry: maps planner tool names to binary + arg templates + target extractors.
The planner fills named slots; the registry renders the real command and extracts
targets for scope checking without relying on a single regex.
"""
from __future__ import annotations

import ipaddress
import re
import shlex
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from agent.policy import Tier


@dataclass
class ToolDef:
    binary: str
    template: list[str]             # placeholders like {domain}, {target}, {url}
    tier: Tier
    needs_root_default: bool = False
    extract: Callable[[dict], list[str]] = field(default_factory=lambda: _no_targets)
    description: str = ""


def _no_targets(_: dict) -> list[str]:
    return []


def _slot(args: dict, *keys: str) -> list[str]:
    out = []
    for k in keys:
        v = args.get(k, "")
        if v:
            out.append(str(v))
    return out


# ── Per-tool target extractors ─────────────────────────────────────────────────

def _extract_nmap(args: dict) -> list[str]:
    raw = args.get("target", "")
    if not raw:
        return []
    return _expand_nmap_target(raw)


def _extract_masscan(args: dict) -> list[str]:
    raw = args.get("target", "")
    if not raw:
        return []
    return _expand_cidr_or_single(raw)


def _extract_url(args: dict) -> list[str]:
    url = args.get("url", "") or args.get("target", "")
    if not url:
        return []
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname or ""
    return [host] if host else []


def _extract_domain(args: dict) -> list[str]:
    return _slot(args, "domain", "host", "target")


def _extract_nuclei(args: dict) -> list[str]:
    target = args.get("target", "") or args.get("url", "")
    if not target:
        return []
    parsed = urlparse(target if "://" in target else f"https://{target}")
    host = parsed.hostname or target
    return [host]


def _expand_nmap_target(raw: str) -> list[str]:
    raw = raw.strip()
    # CIDR notation
    try:
        net = ipaddress.ip_network(raw, strict=False)
        hosts = list(net.hosts())
        if len(hosts) > 512:
            # Too large to enumerate — return the network address for scope check
            return [str(net.network_address), str(net.broadcast_address)]
        return [str(h) for h in hosts] or [str(net.network_address)]
    except ValueError:
        pass
    # Range: 10.0.0.1-50
    m = re.match(r'^(\d+\.\d+\.\d+\.)(\d+)-(\d+)$', raw)
    if m:
        prefix, start, end = m.group(1), int(m.group(2)), int(m.group(3))
        end = min(end, start + 511)
        return [f"{prefix}{i}" for i in range(start, end + 1)]
    # Single IP or hostname
    return [raw]


def _expand_cidr_or_single(raw: str) -> list[str]:
    try:
        net = ipaddress.ip_network(raw, strict=False)
        hosts = list(net.hosts())
        if len(hosts) > 512:
            return [str(net.network_address), str(net.broadcast_address)]
        return [str(h) for h in hosts] or [str(net.network_address)]
    except ValueError:
        return [raw]


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, ToolDef] = {
    "subfinder": ToolDef(
        binary="subfinder",
        template=["-d", "{domain}", "-silent", "-all"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="Passive subdomain enumeration",
    ),
    "httpx": ToolDef(
        binary="httpx",
        template=["-u", "{url}", "-silent", "-status-code", "-title"],
        tier=Tier.RECON,
        extract=_extract_url,
        description="HTTP probe — status, title, tech",
    ),
    "httpx_list": ToolDef(
        binary="httpx",
        template=["-l", "{list_file}", "-silent", "-status-code"],
        tier=Tier.RECON,
        extract=lambda a: [],           # file contents not scope-checkable here
        description="HTTP probe from host list file",
    ),
    "nmap": ToolDef(
        binary="nmap",
        template=["-sV", "-p", "{ports}", "--open", "-oN", "{output}", "{target}"],
        tier=Tier.RECON,
        needs_root_default=True,
        extract=_extract_nmap,
        description="Port/service scan",
    ),
    "nmap_udp": ToolDef(
        binary="nmap",
        template=["-sU", "-p", "{ports}", "--open", "-oN", "{output}", "{target}"],
        tier=Tier.RECON,
        needs_root_default=True,
        extract=_extract_nmap,
        description="UDP port scan",
    ),
    "masscan": ToolDef(
        binary="masscan",
        template=["{target}", "-p", "{ports}", "--rate", "{rate}"],
        tier=Tier.RECON,
        needs_root_default=True,
        extract=_extract_masscan,
        description="Fast port scan via masscan",
    ),
    "naabu": ToolDef(
        binary="naabu",
        template=["-host", "{domain}", "-p", "{ports}", "-silent"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="Fast port discovery",
    ),
    "nuclei_recon": ToolDef(
        binary="nuclei",
        template=["-u", "{url}", "-tags", "recon,info,tech", "-silent", "-nc"],
        tier=Tier.RECON,
        extract=_extract_nuclei,
        description="Nuclei recon/info templates only",
    ),
    "nuclei_exploit": ToolDef(
        binary="nuclei",
        template=["-u", "{url}", "-severity", "high,critical", "-silent", "-nc"],
        tier=Tier.EXPLOIT,
        extract=_extract_nuclei,
        description="Nuclei high/critical exploit templates",
    ),
    "dnsx": ToolDef(
        binary="dnsx",
        template=["-d", "{domain}", "-a", "-cname", "-silent"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="DNS record resolution",
    ),
    "katana": ToolDef(
        binary="katana",
        template=["-u", "{url}", "-d", "{depth}", "-silent", "-nc"],
        tier=Tier.RECON,
        extract=_extract_url,
        description="Web crawler / link spider",
    ),
    "gau": ToolDef(
        binary="gau",
        template=["{domain}"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="Fetch URLs from AlienVault, Wayback, etc.",
    ),
    "waybackurls": ToolDef(
        binary="waybackurls",
        template=["{domain}"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="Fetch URLs from Wayback Machine",
    ),
    "gobuster_dir": ToolDef(
        binary="gobuster",
        template=["dir", "-u", "{url}", "-w", "{wordlist}", "-q", "--no-error"],
        tier=Tier.RECON,
        extract=_extract_url,
        description="Directory bruteforce",
    ),
    "gobuster_dns": ToolDef(
        binary="gobuster",
        template=["dns", "-d", "{domain}", "-w", "{wordlist}", "-q"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="DNS subdomain bruteforce",
    ),
    "whatweb": ToolDef(
        binary="whatweb",
        template=["{url}", "--color=never", "-q"],
        tier=Tier.RECON,
        extract=_extract_url,
        description="Web technology fingerprinting",
    ),
    "curl": ToolDef(
        binary="curl",
        template=["-sk", "-L", "--max-time", "10", "{url}"],
        tier=Tier.RECON,
        extract=_extract_url,
        description="HTTP request / content fetch",
    ),
    "curl_post": ToolDef(
        binary="curl",
        template=["-sk", "-X", "POST", "-d", "{data}", "{url}"],
        tier=Tier.EXPLOIT,
        extract=_extract_url,
        description="HTTP POST request",
    ),
    "dig": ToolDef(
        binary="dig",
        template=["+short", "{record_type}", "{domain}"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="DNS lookup",
    ),
    "whois": ToolDef(
        binary="whois",
        template=["{domain}"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="Domain WHOIS lookup",
    ),
    "amass": ToolDef(
        binary="amass",
        template=["enum", "-passive", "-d", "{domain}", "-silent"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="Passive OSINT subdomain enum",
    ),
    "tlsx": ToolDef(
        binary="tlsx",
        template=["-u", "{domain}", "-silent"],
        tier=Tier.RECON,
        extract=_extract_domain,
        description="TLS certificate inspection",
    ),
    "tcpdump": ToolDef(
        binary="tcpdump",
        template=["-i", "{interface}", "-n", "-c", "{count}", "{filter}"],
        tier=Tier.RECON,
        needs_root_default=True,
        extract=_no_targets,
        description="Packet capture (local traffic)",
    ),
    "sqlmap": ToolDef(
        binary="sqlmap",
        template=["-u", "{url}", "--batch", "--level", "{level}", "--risk", "{risk}"],
        tier=Tier.EXPLOIT,
        extract=_extract_url,
        description="SQL injection testing",
    ),
    "ffuf": ToolDef(
        binary="ffuf",
        template=["-u", "{url}", "-w", "{wordlist}", "-c", "-mc", "200,301,302,403"],
        tier=Tier.EXPLOIT,
        extract=_extract_url,
        description="Web fuzzing (content discovery / params)",
    ),
    "raw": ToolDef(
        binary="sh",
        template=["-c", "{cmd}"],
        tier=Tier.EXPLOIT,
        extract=_no_targets,
        description="Raw shell command (always requires explicit approval)",
    ),
    "browser": ToolDef(
        binary="browser",
        template=[],
        tier=Tier.RECON,
        extract=_no_targets,
        description="Stateful headless browser (DOM action loop)",
    ),
    "caido_history": ToolDef(
        binary="caido",
        template=[],
        tier=Tier.RECON,
        extract=lambda args: _slot(args, "host", "host_filter"),
        description="Pull HTTP history from Caido proxy for a host | slots: host, limit",
    ),
    "caido_create_finding": ToolDef(
        binary="caido",
        template=[],
        tier=Tier.EXPLOIT,
        extract=lambda args: _slot(args, "host"),
        description="Create a Caido finding for a confirmed vulnerability | slots: request_id, title, description, host",
    ),
}


STATEFUL_TOOLS: set[str] = {"browser", "caido_history", "caido_create_finding"}

BROWSER_ACTIONS: set[str] = {
    "goto", "back", "extract", "screenshot",
    "click", "type", "submit",
}

_BROWSER_TIER_MAP: dict[str, Tier] = {
    "goto":       Tier.RECON,
    "back":       Tier.RECON,
    "extract":    Tier.RECON,
    "screenshot": Tier.RECON,
    "click":      Tier.EXPLOIT,
    "type":       Tier.EXPLOIT,
    "submit":     Tier.EXPLOIT,
}


def browser_action_tier(op: str) -> Tier:
    """Default tier per browser op. Unknown ops → EXPLOIT (fail-closed)."""
    return _BROWSER_TIER_MAP.get(op, Tier.EXPLOIT)


def browser_help_block() -> str:
    return (
        "Stateful browser tool: emit {\"tool\": \"browser\", \"action\": {...}, \"tier\": ..., ...}.\n"
        "  Actions:\n"
        "    {\"op\": \"goto\",       \"url\": \"https://host/path\"}   (recon)\n"
        "    {\"op\": \"extract\"}                                       (recon, page text)\n"
        "    {\"op\": \"screenshot\"}                                    (recon, PNG bytes)\n"
        "    {\"op\": \"back\"}                                          (recon)\n"
        "    {\"op\": \"click\",      \"id\": <int>}                       (exploit)\n"
        "    {\"op\": \"type\",       \"id\": <int>, \"value\": \"<text>\"} (exploit)\n"
        "    {\"op\": \"submit\",     \"id\": <int>}                       (exploit, Enter key)\n"
        "  Element ids come from the most-recent observe() result fed back in the result message.\n"
        "  Scope is re-checked after every action — a redirect off-scope hard-stops the session."
    )


def render(tool_name: str, args: dict) -> tuple[str, list[str]]:
    """Render tool + args dict into (binary, argv_list). Raise KeyError if unknown tool."""
    defn = REGISTRY[tool_name]
    argv: list[str] = []
    for part in defn.template:
        if part.startswith("{") and part.endswith("}"):
            key = part[1:-1]
            val = args.get(key, "")
            if val:
                argv.append(str(val))
            # empty optional slot → skip
        else:
            argv.append(part)
    return defn.binary, argv


def extract_targets(tool_name: str, args: dict) -> list[str]:
    """Extract target hosts/IPs/CIDRs from the planner's args for scope checking."""
    defn = REGISTRY.get(tool_name)
    if defn is None:
        return []
    return defn.extract(args)


def tool_registry_summary() -> str:
    """Human-readable tool list for the planner's system prompt."""
    lines = []
    for name, defn in REGISTRY.items():
        if name in {"raw", *STATEFUL_TOOLS}:
            continue
        slots = [p[1:-1] for p in defn.template if p.startswith("{")]
        root = " [root]" if defn.needs_root_default else ""
        lines.append(f"  {name}: {defn.description}{root} | slots: {', '.join(slots)}")
    return "\n".join(lines)
