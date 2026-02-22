"""Judge — policy gate for all HAL actions. Every action goes through here."""
from datetime import datetime
from pathlib import Path

from rich.console import Console

AUDIT_LOG = Path.home() / ".orion" / "audit.log"

TIERS = {
    0: "read-only",
    1: "modify (reversible)",
    2: "config change",
    3: "destructive",
}

# Shell command patterns → minimum tier
_CMD_RULES: list[tuple[int, list[str]]] = [
    (3, ["rm -rf", "drop table", "mkfs", "dd if=", ":(){:|:&};:"]),
    (2, ["docker run", "systemctl enable", "systemctl disable", "chmod 777", "ufw", "> /etc"]),
    (1, ["docker restart", "docker stop", "docker start",
         "systemctl restart", "systemctl stop", "systemctl start"]),
]

# Fixed tiers for non-command action types
_ACTION_TIERS: dict[str, int] = {
    "read_file":    0,
    "list_dir":     0,
    "write_file":   2,
    "search_kb":    0,
    "get_metrics":  0,
    "remember_fact": 0,
}

console = Console()


def classify_command(command: str) -> int:
    """Return the tier for a shell command based on pattern matching."""
    lower = command.lower()
    for tier, patterns in _CMD_RULES:
        if any(p in lower for p in patterns):
            return tier
    return 0


def tier_for(action_type: str, detail: str = "") -> int:
    """Return the appropriate tier for a given action type."""
    if action_type == "run_command":
        return classify_command(detail)
    return _ACTION_TIERS.get(action_type, 1)


class Judge:
    """Policy gate: classify → prompt if needed → log every decision."""

    def __init__(self, audit_log: Path = AUDIT_LOG):
        self.audit_log = audit_log
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)

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
            self._log(action_type, detail, tier, approved=True, auto=True)
            return True

        approved = self._request_approval(action_type, detail, tier, reason)
        self._log(action_type, detail, tier, approved=approved, auto=False)
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
    ) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        status = "auto    " if auto else ("approved" if approved else "denied  ")
        log_detail = detail.replace("\n", " ")[:200]
        entry = f"{ts} | tier={tier} | {status} | {action_type:<14} | {log_detail}\n"
        with open(self.audit_log, "a") as f:
            f.write(entry)
