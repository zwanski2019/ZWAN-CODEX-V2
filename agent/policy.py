from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from agent.scope import Scope


class Decision(Enum):
    ALLOW_AUTO = "allow_auto"
    NEEDS_APPROVAL = "needs_approval"
    BLOCK = "block"


class Mode(Enum):
    MANUAL = "manual"
    AUTO = "auto"
    YOLO = "yolo"


class Tier(Enum):
    RECON = "recon"
    EXPLOIT = "exploit"


SUDO_ALLOWLIST = {"nmap", "masscan", "naabu", "tcpdump"}
READONLY_ALLOWLIST = {
    "subfinder", "httpx", "naabu", "nuclei", "dnsx", "katana", "gau",
    "waybackurls", "gobuster", "whatweb", "curl", "dig", "whois", "amass", "tlsx",
}

# Damages the operator's OWN box — never auto, regardless of mode.
_SYS_DESTRUCTIVE_BINS = {"rm", "dd", "mkfs", "shutdown", "reboot", "kill",
                         "killall", "chown", "chmod", "fdisk", "parted", "userdel"}
_SYS_DESTRUCTIVE_RE = re.compile(r"(>|>>)\s*/(etc|usr|bin|boot|var|lib|sys)\b|iptables\s+-F|:\(\)\s*\{")


@dataclass
class ParsedCommand:
    binary: str
    args: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    needs_root: bool = False
    tier: Tier = Tier.EXPLOIT          # fail-closed: unknown → treated as exploit

    @property
    def rendered(self) -> str:
        return " ".join([self.binary, *self.args])

    def is_system_destructive(self) -> bool:
        if self.binary in _SYS_DESTRUCTIVE_BINS:
            return True
        return bool(_SYS_DESTRUCTIVE_RE.search(self.rendered))


def evaluate(cmd: ParsedCommand, mode: Mode, scope: Scope, dry_run: bool = False) -> Decision:
    # 1. SCOPE — hard block, every mode, no exceptions.
    for t in cmd.targets:
        if not scope.contains(t):
            return Decision.BLOCK
    # 2. ROOT must be allowlisted.
    if cmd.needs_root and cmd.binary not in SUDO_ALLOWLIST:
        return Decision.BLOCK
    # 3. Protect the operator's own machine.
    if cmd.is_system_destructive():
        return Decision.NEEDS_APPROVAL
    # 4. Mode x tier.
    if mode is Mode.MANUAL:
        return Decision.NEEDS_APPROVAL
    if mode is Mode.YOLO:
        return Decision.ALLOW_AUTO
    if cmd.tier is Tier.RECON and (cmd.binary in READONLY_ALLOWLIST or cmd.binary == "browser"):
        return Decision.ALLOW_AUTO
    return Decision.NEEDS_APPROVAL     # AUTO + exploit → staged for one-click
