"""Judge — policy gate for all HAL actions. Every action goes through here."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from hal.llm import VLLMClient

AUDIT_LOG = Path.home() / ".orion" / "audit.log"

TIERS = {
    0: "read-only",
    1: "modify (reversible)",
    2: "config change",
    3: "destructive",
}

# Shell command patterns → minimum tier (checked in order, first match wins)
# NOTE: these are substring matches against the lowercased full command.
# Use trailing spaces or specific flags to avoid false positives on short words.
_CMD_RULES: list[tuple[int, list[str]]] = [
    (
        3,
        [
            # Original destructive patterns
            "rm -rf",
            "rm -f",
            "drop table",
            "mkfs",
            "dd if=",
            ":(){:|:&};:",
            # Disk / partition destruction
            "shred ",
            "wipefs",
            "fdisk ",
            "parted ",
            # System halt / reboot
            "reboot",
            "shutdown",
            "poweroff",
            "halt",
            "init 0",
            "init 6",
            "telinit",
            # Firewall flush (drops all rules — locks you out)
            "iptables -f",
            "iptables --flush",
            "nft flush",
            # Crontab removal
            "crontab -r",
            # Filesystem mount/unmount (can corrupt data)
            "umount ",
            "swapoff",
        ],
    ),
    (
        2,
        [
            # Original config-change patterns
            "docker run",
            "systemctl enable",
            "systemctl disable",
            "chmod 777",
            "ufw",
            "> /etc",
            # Scripting interpreters running inline code
            "python -c",
            "python3 -c",
            "perl -e",
            "ruby -e",
            "node -e",
            # Setuid / ownership changes
            "chmod +s",
            "chmod u+s",
            "chmod g+s",
            "chown ",
            "chgrp ",
            # User / group management
            "useradd",
            "userdel",
            "usermod",
            "groupadd",
            "groupdel",
            "visudo",
            # Scheduled task editing
            "crontab -e",
            # Mount (read-write by default)
            "mount ",
        ],
    ),
    (
        1,
        [
            "docker restart",
            "docker stop",
            "docker start",
            "systemctl restart",
            "systemctl stop",
            "systemctl start",
        ],
    ),
]

# Paths that should never be auto-approved (tier 0 → tier 1)
# These are canonical absolute path prefixes.  _is_sensitive_path()
# canonicalizes the input before matching.  Keep entries as absolute.
_SENSITIVE_PATHS: list[str] = [
    "/run/homelab-secrets",
    os.path.expanduser("~/.ssh"),  # e.g. /home/jp/.ssh
    "/etc/shadow",
    "/etc/gshadow",
    "/etc/sudoers",
    "/etc/passwd",
    "/root",
    "/proc/kcore",
]

# Basename patterns that are sensitive regardless of directory
_SENSITIVE_BASENAMES: frozenset[str] = frozenset(
    {
        ".env",
    }
)

# Safe read-only command first tokens — tier 0 for these
_SAFE_FIRST_TOKENS: frozenset[str] = frozenset(
    {
        # process / resource inspection
        "ps",
        "top",
        "htop",
        "iotop",
        "free",
        "uptime",
        # filesystem / disk
        "df",
        "du",
        "ls",
        "cat",
        "head",
        "tail",
        "stat",
        "lsblk",
        "find",
        "file",
        "which",
        "realpath",
        "readlink",
        "basename",
        "dirname",
        # text processing (read-only)
        "grep",
        "egrep",
        "fgrep",
        "wc",
        "sort",
        "uniq",
        "echo",
        "awk",
        "sed",
        "cut",
        "tr",
        "diff",
        "md5sum",
        "sha256sum",
        # system info
        "uname",
        "hostname",
        "date",
        "id",
        "whoami",
        "pwd",
        "lscpu",
        "lspci",
        "lsusb",
        "lsof",
        "printenv",
        "env",
        "nproc",
        "getconf",
        "timedatectl",
        "hostnamectl",
        "locale",
        # hardware / GPU
        "nvidia-smi",
        "sensors",
        "lsmod",
        # package queries (read-only — list/show only)
        "dpkg-query",
        "rpm",
        # network observation
        "netstat",
        "ss",
        "ip",
        "ping",
        "dig",
        "nslookup",
        "host",
        "traceroute",
        "tracepath",
        "nmcli",
        "resolvectl",
        # logging
        "journalctl",
        # misc read-only
        "last",
        "w",
        "who",
        "dmesg",
    }
)

# Two-token safe prefixes: (first, second) → tier 0
_SAFE_COMPOUND: frozenset[tuple[str, str]] = frozenset(
    {
        # systemctl read-only subcommands
        ("systemctl", "status"),
        ("systemctl", "show"),
        ("systemctl", "is-active"),
        ("systemctl", "is-enabled"),
        ("systemctl", "is-failed"),
        ("systemctl", "list-units"),
        ("systemctl", "list-timers"),
        ("systemctl", "list-sockets"),
        ("systemctl", "list-dependencies"),
        ("systemctl", "cat"),
        # docker read-only subcommands
        ("docker", "ps"),
        ("docker", "stats"),
        ("docker", "logs"),
        ("docker", "inspect"),
        ("docker", "images"),
        ("docker", "network"),
        ("docker", "top"),
        ("docker", "port"),
        ("docker", "info"),
        ("docker", "version"),
        ("docker", "df"),
        # docker compose read-only
        ("docker", "compose"),  # compose ps/logs/top — write ops handled by _CMD_RULES
        # ip read-only subcommands
        ("ip", "addr"),
        ("ip", "address"),
        ("ip", "route"),
        ("ip", "link"),
        ("ip", "neigh"),
        ("ip", "rule"),
        # dnf / apt read-only queries
        ("dnf", "list"),
        ("dnf", "info"),
        ("dnf", "search"),
        ("dnf", "repoquery"),
        ("apt", "list"),
        ("apt", "show"),
        ("apt", "search"),
    }
)

# Fixed tiers for non-command action types
# NOTE: write_file is handled explicitly in tier_for() — not here.
_ACTION_TIERS: dict[str, int] = {
    "search_kb": 0,
    "get_metrics": 0,
    "get_trend": 0,
    "remember_fact": 0,
    "get_action_stats": 0,
    # Security workers — reads are tier 0, active LAN scan is tier 1
    "get_security_events": 0,
    "get_host_connections": 0,
    "get_traffic_summary": 0,
    "scan_lan": 1,
    # Web access — read-only search via external API
    "web_search": 0,
    # Web access — outbound HTTP request to arbitrary URL (needs approval)
    "fetch_url": 1,
    # Recovery — individual steps go through Judge separately
    "recover_component": 1,
}

# ---------------------------------------------------------------------------
# Shell normalisation & evasion detection  (Item 1 — safety hardening)
# ---------------------------------------------------------------------------

# Patterns that indicate shell evasion — unconditional deny (tier 3)
_EVASION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Subshell / command substitution
    (re.compile(r"\$\("), "command substitution $()"),
    (re.compile(r"`[^`]+`"), "backtick command substitution"),
    # eval / exec wrappers
    (re.compile(r"\beval\b"), "eval keyword"),
    (re.compile(r"\bexec\b"), "exec keyword"),
    # Base64 decode piped to shell
    (re.compile(r"base64\s+(-d|--decode).*\|"), "base64 decode pipe"),
    (re.compile(r"\|\s*(ba)?sh\b"), "pipe to shell"),
    (re.compile(r"\|\s*source\b"), "pipe to source"),
    # Process substitution
    (re.compile(r"<\("), "process substitution <()"),
    (re.compile(r">\("), "process substitution >()"),
    # Hex/octal escape sequences (e.g. $'\x72\x6d')
    (re.compile(r"\$'[^']*\\x[0-9a-fA-F]"), "hex escape in $''"),
    (re.compile(r"\$'[^']*\\[0-7]{3}"), "octal escape in $''"),
]

# Tokens used to chain multiple commands
_COMMAND_SEPARATORS = re.compile(r"\s*(?:;|&&|\|\||(?<!\|)\|(?!\|)|\n)\s*")


def _detect_evasion(cmd: str) -> str | None:
    """Return evasion description if cmd uses shell evasion, else None."""
    for pattern, description in _EVASION_PATTERNS:
        if pattern.search(cmd):
            return description
    return None


def _split_compound_command(cmd: str) -> list[str]:
    """Split a compound shell command into individual sub-commands.

    Splits on ; && || | and newlines.  Returns at least one entry.
    Empty fragments (from trailing separators etc.) are dropped.
    """
    parts = _COMMAND_SEPARATORS.split(cmd.strip())
    return [p.strip() for p in parts if p.strip()]


def _normalize_command(cmd: str) -> str:
    """Normalize whitespace and strip leading/trailing junk."""
    return " ".join(cmd.split())


# ---------------------------------------------------------------------------
# Git write-operation blocking  (Item 3 — safety hardening)
# ---------------------------------------------------------------------------

# Git subcommands that modify the repository — unconditional deny (tier 3).
# Read-only subcommands (status, log, diff, show, blame, shortlog, describe,
# ls-files, ls-tree, rev-parse) are NOT listed here and fall through normally.
_GIT_WRITE_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "add",
        "commit",
        "push",
        "merge",
        "rebase",
        "pull",
        "reset",
        "revert",
        "cherry-pick",
        "am",
        "apply",
        "tag",
        "branch",
        "checkout",
        "switch",
        "remote",
        "fetch",  # fetch is safe but remote add/set-url is not — block both, allow via override
        "clean",
        "gc",
        "prune",
        "stash",  # stash drop/clear can destroy work
        "rm",
        "mv",
        "submodule",
        "bisect",
        "init",
        "clone",
        "config",  # can set credentials, hooks, aliases
    }
)

# Git subcommands that are always read-only — tier 0
_GIT_SAFE_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "blame",
        "shortlog",
        "describe",
        "ls-files",
        "ls-tree",
        "rev-parse",
        "rev-list",
        "reflog",
        "--version",
        "help",
        "--no-pager",
    }
)


def _classify_git_command(parts: list[str]) -> int | None:
    """Classify a git command. Returns tier or None if not a git command.

    Policy: server may never write to git. Read-only git ops are tier 0.
    Write ops are unconditional tier 3 (destructive — policy violation).
    """
    if not parts:
        return None
    base = parts[0].rsplit("/", 1)[-1].lower()
    if base != "git":
        return None

    # 'git' with no subcommand
    if len(parts) < 2:
        return 0  # bare 'git' just shows help

    # Skip flags to find the subcommand (e.g. 'git --no-pager log')
    sub = None
    for token in parts[1:]:
        if not token.startswith("-"):
            sub = token.lower()
            break
        # --no-pager is itself a safe token
        if token.lower() in _GIT_SAFE_SUBCOMMANDS:
            return 0

    if sub is None:
        return 0  # only flags, no subcommand

    if sub in _GIT_SAFE_SUBCOMMANDS:
        return 0
    if sub in _GIT_WRITE_SUBCOMMANDS:
        return 3  # unconditional deny — policy: no git writes on server
    # Unknown git subcommand — treat as write (default-deny)
    return 3


# ---------------------------------------------------------------------------
# Path canonicalization  (Item 4 — safety hardening)
# ---------------------------------------------------------------------------

# Repo root — resolved at import time.  write_file to anything under this
# path is unconditionally denied (policy: propose only, never apply).
_REPO_ROOT: str = str(Path(__file__).resolve().parent.parent)


def _canonicalize_path(path: str) -> str:
    """Expand ~ and resolve symlinks / .. / double-slashes to a canonical path."""
    return os.path.realpath(os.path.expanduser(path))


def _is_repo_path(path: str) -> bool:
    """Return True if *path* resolves to a location under the Orion repo root."""
    canonical = _canonicalize_path(path)
    return canonical == _REPO_ROOT or canonical.startswith(_REPO_ROOT + "/")


console = Console()


def _is_sensitive_path(path: str) -> bool:
    """Check if *path* resolves to a sensitive location.

    Handles: ~, .., //, symlinks, and basename patterns like '.env'.
    """
    # 1. Check basename patterns (works for bare filenames like '.env')
    basename = os.path.basename(path.rstrip("/"))
    if basename in _SENSITIVE_BASENAMES:
        return True

    # 2. Canonicalize and check prefix matches against _SENSITIVE_PATHS
    canonical = _canonicalize_path(path)
    return any(canonical.startswith(sp) for sp in _SENSITIVE_PATHS)


def _command_touches_sensitive_path(command: str) -> bool:
    """Check if any argument in a shell command refers to a sensitive path.

    Extracts path-like tokens (starting with /, ~, or containing .env)
    from the command and checks each against _is_sensitive_path.
    """
    parts = command.strip().split()
    for token in parts[1:]:  # skip the command itself
        # Strip leading flags like --file=/etc/shadow
        if "=" in token:
            token = token.split("=", 1)[1]
        # Check tokens that look like paths or sensitive basenames
        if (
            token.startswith("/")
            or token.startswith("~")
            or token.startswith(".")
            or os.path.basename(token) in _SENSITIVE_BASENAMES
        ):
            if _is_sensitive_path(token):
                return True
    return False


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
    """Return the tier for a shell command.

    Normalizes the command, checks for evasion patterns, splits compound
    commands, and returns the *highest* tier across all sub-commands.
    """
    normalized = _normalize_command(command)

    # 1. Unconditional deny on evasion patterns (before splitting —
    #    evasion can span the whole string)
    evasion = _detect_evasion(normalized)
    if evasion:
        return 3

    # 2. Check _CMD_RULES against the full command BEFORE splitting —
    #    some patterns (e.g. fork bomb) span separator characters
    lower_full = normalized.lower()
    for tier, patterns in _CMD_RULES:
        if any(p in lower_full for p in patterns):
            return tier

    # 3. Split compound commands and evaluate each sub-command
    sub_commands = _split_compound_command(normalized)
    if not sub_commands:
        return 2  # empty command — uncertain, require approval

    worst_tier = 0
    for sub in sub_commands:
        tier = _classify_single_command(sub)
        if tier > worst_tier:
            worst_tier = tier

    return worst_tier


def _classify_single_command(command: str) -> int:
    """Classify a single (non-compound) shell command."""
    lower = command.lower()

    # 1. Known dangerous patterns take priority
    for tier, patterns in _CMD_RULES:
        if any(p in lower for p in patterns):
            return tier

    # 2. Handle sudo: strip it and re-classify the inner command
    parts = command.strip().split()
    if parts and parts[0].lower() == "sudo":
        inner = command.strip().split(maxsplit=1)
        if len(inner) > 1:
            return max(1, _classify_single_command(inner[1]))
        return 2  # bare sudo

    # 3. Git write-operation blocking (policy: no git writes on server)
    git_tier = _classify_git_command(parts)
    if git_tier is not None:
        return git_tier

    # 4. Strip leading path for first-token matching
    #    e.g. /usr/bin/cat → cat
    if parts:
        base = parts[0].rsplit("/", 1)[-1].lower()
        parts_copy = [base] + parts[1:]
        if _is_safe_command(" ".join(parts_copy)):
            # Re-check sensitive paths even for safe commands
            if _command_touches_sensitive_path(command):
                return 1
            return 0

    # 5. Sensitive paths bump to tier 1
    if _command_touches_sensitive_path(command):
        return 1

    # 6. Explicit safe allowlist → tier 0
    if _is_safe_command(command):
        return 0

    # 7. Unknown command — default-deny (explain + approve)
    return 2


def tier_for(action_type: str, detail: str = "") -> int:
    """Return the appropriate tier for a given action type."""
    if action_type == "run_command":
        return classify_command(detail)

    if action_type in ("read_file", "list_dir"):
        # Canonicalize paths before sensitive-path check
        return 1 if _is_sensitive_path(detail) else 0

    if action_type == "write_file":
        # Policy: HAL may never write to its own repo on the server.
        # This enforces "propose only, never apply".
        if _is_repo_path(detail):
            return 3  # unconditional deny — self-edit policy violation
        # Non-repo writes still require config-change approval
        if _is_sensitive_path(detail):
            return 3  # sensitive paths are destructive-tier for writes
        return 2

    return _ACTION_TIERS.get(action_type, 2)


# ---------------------------------------------------------------------------
# Trust evolution helpers
# ---------------------------------------------------------------------------

# Minimum outcome samples required before a tier reduction is considered.
# why: too few samples means a lucky streak can reduce trust prematurely.
_TRUST_MIN_SAMPLES = 10

# Minimum success rate (0.0–1.0) required to reduce tier 1 → tier 0.
# why: 90% allows for the occasional transient error without blocking evolution,
# while still rejecting commands that fail 1-in-5 times.
_TRUST_MIN_SUCCESS_RATE = 0.90

# Success rate below which an earned trust override is explicitly revoked.
# why: a command that was once reliable but now fails >30% of the time should
# lose its auto-approval and alert the operator.  The gap between 0.70 and 0.90
# is intentional — it prevents rapid flip-flopping between promoted and demoted.
_TRUST_DEMOTION_RATE = 0.70


def _trust_key(action_type: str, detail: str) -> str:
    """Compute a stable grouping key for trust tracking.

    For run_command, uses 'run_command:<first_token>' so 'ps aux' and
    'ps -ef' both contribute to the same 'ps' trust bucket.
    For all other action types, the key is the action type itself.

    # why: grouping by first token lets trust accumulate across argument
    # variations of the same command (e.g. systemctl restart X vs Y) rather
    # than requiring each exact invocation to independently earn trust.
    """
    if action_type == "run_command":
        first = detail.strip().split()[0] if detail.strip() else detail
        return f"run_command:{first}"
    return action_type


def _load_trust_overrides(
    audit_log: Path,
    demotion_rate: float = _TRUST_DEMOTION_RATE,
) -> tuple[dict[str, int], frozenset[str]]:
    """Read audit log outcome entries and return evolved tier overrides.

    Returns a tuple of:
    - overrides: ``{trust_key: 0}`` for promoted actions (≥10 samples, ≥90% success)
    - demotions: frozenset of trust keys whose success rate dropped below
      ``demotion_rate`` with ≥10 samples.  Demoted keys are never promoted,
      even if their cumulative rate later recovers — the demotion entry
      persists in the audit log as a signal to the operator.

    Only tier-1 actions (reversible modifications) are candidates for promotion.
    Tier 2+ are never reduced.
    """
    if not audit_log.exists():
        return {}, frozenset()

    counts: dict[str, list[bool]] = {}
    demoted_keys: set[str] = set()
    try:
        with open(audit_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Track previously logged demotions so we don't re-log them
                if entry.get("status") == "trust_demotion":
                    key = _trust_key(entry.get("action", ""), entry.get("detail", ""))
                    demoted_keys.add(key)
                    continue
                if entry.get("status") != "outcome":
                    continue
                key = _trust_key(entry.get("action", ""), entry.get("detail", ""))
                success = entry.get("outcome") == "success"
                counts.setdefault(key, []).append(success)
    except OSError:
        return {}, frozenset()

    overrides: dict[str, int] = {}
    new_demotions: set[str] = set()
    for key, results in counts.items():
        if len(results) < _TRUST_MIN_SAMPLES:
            continue
        rate = sum(results) / len(results)

        # Demotion check: rate dropped below threshold
        if rate < demotion_rate:
            new_demotions.add(key)
            continue

        # Promotion check: rate is high enough AND key is not demoted
        if rate >= _TRUST_MIN_SUCCESS_RATE and key not in demoted_keys:
            overrides[key] = 0

    # Merge newly-detected demotions with previously-logged ones
    all_demotions = demoted_keys | new_demotions

    # Log newly-demoted keys (only keys not already logged as demoted)
    for key in new_demotions - demoted_keys:
        _entry = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "trust_demotion",
            "action": key.split(":", 1)[0] if ":" in key else key,
            "detail": key.split(":", 1)[1] if ":" in key else "",
            "reason": f"success rate dropped below {demotion_rate:.0%}",
        }
        try:
            with open(audit_log, "a") as f:
                f.write(json.dumps(_entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    return overrides, frozenset(all_demotions)


class Judge:
    """Policy gate: classify → prompt if needed → log every decision."""

    def __init__(
        self,
        audit_log: Path = AUDIT_LOG,
        llm: VLLMClient | None = None,
        extra_sensitive_paths: tuple[str, ...] = (),
    ):
        self.audit_log = audit_log
        self.llm = llm
        self._extra_sensitive: tuple[str, ...] = tuple(
            os.path.expanduser(p) for p in extra_sensitive_paths if p
        )
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        # Cache computed overrides and the log size at load time.
        # why: recomputing on every approve() call would re-read the entire
        # audit log on each action — cache it and only reload when the log grows.
        overrides, demotions = _load_trust_overrides(self.audit_log)
        self._trust_overrides: dict[str, int] = overrides
        self._trust_demotions: frozenset[str] = demotions
        self._audit_log_size: int = (
            self.audit_log.stat().st_size if self.audit_log.exists() else 0
        )

    def _llm_reason(self, action_type: str, detail: str, reason: str) -> str | None:
        """Ask the LLM for a one-sentence risk assessment. Returns None on failure."""
        if not self.llm:
            return None
        try:
            return self.llm.chat(
                [
                    {
                        "role": "user",
                        "content": (
                            f"Action type: {action_type}\n"
                            f"Detail: {detail[:300]}\n"
                            f"Reason: {reason or 'not stated'}\n\n"
                            "In one sentence: is this routine/safe or does it carry risk?"
                        ),
                    }
                ],
                system=(
                    "You are a security evaluator for a homelab automation system. "
                    "Respond with plain text only — do not call any tools or fetch external data. "
                    "Be brief and specific about any risks. No preamble."
                ),
                timeout=15,
            ).strip()
        except Exception:
            return None

    def _extra_tier(self, action_type: str, detail: str) -> int:
        """Return the minimum tier imposed by extra_sensitive_paths for this action.

        Additive-only: results are max()'d with the base tier in approve().
        """
        if not self._extra_sensitive:
            return 0
        canonical = os.path.realpath(os.path.expanduser(detail)) if detail else ""
        if action_type in ("read_file", "list_dir"):
            if any(canonical.startswith(p) for p in self._extra_sensitive):
                return 1
        elif action_type == "write_file":
            if any(canonical.startswith(p) for p in self._extra_sensitive):
                return 3
        elif action_type == "run_command":
            # Check each token of the command for path matches
            for token in detail.strip().split()[1:]:
                if "=" in token:
                    token = token.split("=", 1)[1]
                if token.startswith("/") or token.startswith("~"):
                    t = os.path.realpath(os.path.expanduser(token))
                    if any(t.startswith(p) for p in self._extra_sensitive):
                        return 1
        return 0

    def _refresh_trust_overrides(self) -> None:
        """Reload trust overrides if the audit log has grown since last load.

        # why: checking file size is cheaper than reading the whole log on
        # every approve() call, and new outcome entries only append to the end.
        """
        if not self.audit_log.exists():
            return
        current_size = self.audit_log.stat().st_size
        if current_size != self._audit_log_size:
            overrides, demotions = _load_trust_overrides(self.audit_log)
            self._trust_overrides = overrides
            self._trust_demotions = demotions
            self._audit_log_size = current_size

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

        # Additive extension: extra_sensitive_paths can only raise the tier.
        tier = max(tier, self._extra_tier(action_type, detail))

        # Apply trust evolution: a tier-1 action with a strong track record
        # is reduced to tier 0 so the operator isn't prompted for proven-safe work.
        # why: trust must be earned through outcomes, not assumed from static rules.
        if tier == 1:
            self._refresh_trust_overrides()
            key = _trust_key(action_type, detail)
            # Demoted keys are never promoted — operator must investigate
            if key not in self._trust_demotions and key in self._trust_overrides:
                tier = self._trust_overrides[key]

        if tier == 0:
            self._log(
                action_type, detail, tier, approved=True, auto=True, reason=reason
            )
            return True

        approved = self._request_approval(action_type, detail, tier, reason)
        self._log(
            action_type, detail, tier, approved=approved, auto=False, reason=reason
        )
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
        """Write a structured JSON audit entry.

        Fields: ts, tier, status, action, detail, reason,
        session_id, trace_id (from contextvars if available).
        """
        status = "auto" if auto else ("approved" if approved else "denied")
        entry: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "tier": tier,
            "status": status,
            "action": action_type,
            "detail": detail.replace("\n", " ")[:500],
        }
        if reason:
            entry["reason"] = reason[:200]

        # Session correlation from logging_utils contextvars
        try:
            from hal.logging_utils import _ctx_session_id, _ctx_turn_id

            sid = _ctx_session_id.get()
            tid = _ctx_turn_id.get()
            if sid:
                entry["session_id"] = sid
            if tid:
                entry["turn_id"] = tid
        except Exception:
            pass

        # OTel trace correlation
        try:
            from opentelemetry import trace  # type: ignore[import-untyped]

            span = trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                entry["trace_id"] = f"{ctx.trace_id:032x}"
                entry["span_id"] = f"{ctx.span_id:016x}"
        except Exception:
            pass

        with open(self.audit_log, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record_outcome(
        self,
        action_type: str,
        detail: str,
        outcome: str,
    ) -> None:
        """Append an outcome entry to the audit log after a tool executes.

        outcome is 'success' or 'error'. Correlates with the preceding
        approval entry via session_id / trace_id for trust evolution (B-2).
        """
        entry: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "outcome",
            "outcome": outcome,
            "action": action_type,
            "detail": detail.replace("\n", " ")[:500],
        }

        # Session correlation from logging_utils contextvars
        try:
            from hal.logging_utils import _ctx_session_id, _ctx_turn_id

            sid = _ctx_session_id.get()
            tid = _ctx_turn_id.get()
            if sid:
                entry["session_id"] = sid
            if tid:
                entry["turn_id"] = tid
        except Exception:
            pass

        # OTel trace correlation
        try:
            from opentelemetry import trace  # type: ignore[import-untyped]

            span = trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                entry["trace_id"] = f"{ctx.trace_id:032x}"
                entry["span_id"] = f"{ctx.span_id:016x}"
        except Exception:
            pass

        with open(self.audit_log, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
