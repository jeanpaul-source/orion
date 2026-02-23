"""Judge — policy gate for all HAL actions. Every action goes through here."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from hal.llm import OllamaClient

AUDIT_LOG = Path.home() / ".orion" / "audit.log"

TIERS = {
    0: "read-only",
    1: "modify (reversible)",
    2: "config change",
    3: "destructive",
}

# Shell command patterns → minimum tier (checked in order, first match wins)
_CMD_RULES: list[tuple[int, list[str]]] = [
    (3, ["rm -rf", "drop table", "mkfs", "dd if=", ":(){:|:&};:"]),
    (2, ["docker run", "systemctl enable", "systemctl disable", "chmod 777", "ufw", "> /etc"]),
    (1, ["docker restart", "docker stop", "docker start",
         "systemctl restart", "systemctl stop", "systemctl start"]),
]

# Paths that should never be auto-approved (tier 0 → tier 1)
_SENSITIVE_PATHS: list[str] = [
    "/run/homelab-secrets",
    "/.ssh",
    "~/.ssh",
    "/etc/shadow",
    "/etc/passwd",
    "/root/",
    ".env",
]

# Safe read-only command first tokens — tier 0 for these
_SAFE_FIRST_TOKENS: frozenset[str] = frozenset({
    # process / resource inspection
    "ps", "top", "htop", "iotop", "free", "uptime",
    # filesystem / disk
    "df", "ls", "cat", "head", "tail", "stat", "lsblk", "find",
    # text processing (read-only)
    "grep", "egrep", "fgrep", "wc", "sort", "uniq", "echo",
    # system info
    "uname", "hostname", "date", "id", "whoami", "pwd",
    "lscpu", "lspci", "lsusb", "lsof", "printenv", "env",
    # network observation
    "netstat", "ss", "ip", "ping",
    # logging
    "journalctl",
})

# Two-token safe prefixes: (first, second) → tier 0
_SAFE_COMPOUND: frozenset[tuple[str, str]] = frozenset({
    ("systemctl", "status"),
    ("docker", "ps"),
    ("docker", "stats"),
    ("docker", "logs"),
    ("docker", "inspect"),
    ("docker", "images"),
    ("docker", "network"),
})

# Fixed tiers for non-command action types
_ACTION_TIERS: dict[str, int] = {
    "write_file":   2,
    "search_kb":    0,
    "get_metrics":  0,
    "remember_fact": 0,
}

console = Console()


def _is_sensitive_path(path: str) -> bool:
    return any(p in path for p in _SENSITIVE_PATHS)


def _is_safe_command(command: str) -> bool:
    """Return True if the command is on the read-only safe allowlist."""
    parts = command.strip().split()
    if not parts:
        return False
    first = parts[0].lower()
    if first in _SAFE_FIRST_TOKENS:
        return True
    if len(parts) >= 2:
        second = parts[1].lower()
        if (first, second) in _SAFE_COMPOUND:
            return True
    return False


def classify_command(command: str) -> int:
    """Return the tier for a shell command."""
    lower = command.lower()

    # 1. Known dangerous patterns take priority
    for tier, patterns in _CMD_RULES:
        if any(p in lower for p in patterns):
            return tier

    # 2. Sensitive paths bump unknown-safe commands to tier 1
    if _is_sensitive_path(lower):
        return 1

    # 3. Explicit safe allowlist → tier 0
    if _is_safe_command(command):
        return 0

    # 4. Unknown command — ask before running
    return 1


def tier_for(action_type: str, detail: str = "") -> int:
    """Return the appropriate tier for a given action type."""
    if action_type == "run_command":
        return classify_command(detail)

    if action_type in ("read_file", "list_dir"):
        # detail = the file/dir path
        return 1 if _is_sensitive_path(detail) else 0

    return _ACTION_TIERS.get(action_type, 1)


class Judge:
    """Policy gate: classify → prompt if needed → log every decision."""

    def __init__(
        self,
        audit_log: Path = AUDIT_LOG,
        llm: VLLMClient | None = None,
    ):
        self.audit_log = audit_log
        self.llm = llm
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)

    def _llm_reason(self, action_type: str, detail: str, reason: str) -> str | None:
        """Ask the LLM for a one-sentence risk assessment. Returns None on failure."""
        if not self.llm:
            return None
        try:
            return self.llm.chat(
                [{"role": "user", "content": (
                    f"Action type: {action_type}\n"
                    f"Detail: {detail[:300]}\n"
                    f"Reason: {reason or 'not stated'}\n\n"
                    "In one sentence: is this routine/safe or does it carry risk?"
                )}],
                system=(
                    "You are a security evaluator for a homelab automation system. "
                    "Respond with plain text only — do not call any tools or fetch external data. "
                    "Be brief and specific about any risks. No preamble."
                ),
                timeout=15,
            ).strip()
        except Exception:
            return None

    def approve(
        self,
        action_type: str,
        detail: str,
        tier: int | None = None,
        reason: str = "",
    ) -> bool:
        """Gate an action. Returns True if approved to proceed."""
        if tier is None:
            tier = tier_for(action_type, detail)

        if tier == 0:
            self._log(action_type, detail, tier, approved=True, auto=True, reason=reason)
            return True

        approved = self._request_approval(action_type, detail, tier, reason)
        self._log(action_type, detail, tier, approved=approved, auto=False, reason=reason)
        return approved

    def _request_approval(
        self, action_type: str, detail: str, tier: int, reason: str
    ) -> bool:
        console.print(
            f"\n  [yellow][tier {tier} — {TIERS[tier]}][/] [bold]{action_type}[/]"
        )
        if reason:
            console.print(f"  reason : {reason}")
        display = detail if len(detail) <= 120 else detail[:120] + "..."
        console.print(f"  detail : {display}")
        llm_note = self._llm_reason(action_type, detail, reason)
        if llm_note:
            console.print(f"  [dim]llm eval: {llm_note}[/]")

        if tier >= 3:
            console.print("  [red bold]WARNING: destructive — cannot be undone.[/]")
            try:
                answer = input('  type "YES I CONFIRM" to proceed: ').strip()
            except (KeyboardInterrupt, EOFError):
                answer = ""
            return answer == "YES I CONFIRM"
        else:
            try:
                answer = input("  approve? [y/N] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                answer = "n"
            return answer == "y"

    def _log(
        self,
        action_type: str,
        detail: str,
        tier: int,
        approved: bool,
        auto: bool,
        reason: str = "",
    ) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        status = "auto    " if auto else ("approved" if approved else "denied  ")
        log_detail = detail.replace("\n", " ")[:200]
        reason_str = f" | {reason[:100]}" if reason else ""
        entry = f"{ts} | tier={tier} | {status} | {action_type:<14} | {log_detail}{reason_str}\n"
        with open(self.audit_log, "a") as f:
            f.write(entry)
