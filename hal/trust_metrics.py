"""Trust metrics — parse Judge audit log and compute simple action statistics.

Provides:
- load_audit_log(path): parse ~/.orion/audit.log entries into AuditEvent objects
- aggregate_stats(events): aggregate counts by tool and by action_class
- get_action_stats(pattern, path=None): filter+aggregate by a substring/regex pattern

Audit log format (from hal/judge.py::_log):
  f"{ts} | tier={tier} | {status} | {action_type:<14} | {log_detail}{reason_str}\n"
Where:
  - ts: ISO 8601, seconds precision (e.g., 2026-02-24T13:42:01)
  - status: "auto    " (padded), "approved", or "denied  " (padded)
  - action_type: fixed width 14 chars, left-justified (we strip())
  - detail: command/path/detail (newlines replaced with spaces, max 200 chars)
  - optional reason: prefixed with " | "

We parse len(parts) in {4,5} when splitting on " | ". Lines that do not match
are skipped (robust to future tweaks).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEvent:
    ts: datetime
    tier: int
    status: str  # "auto" | "approved" | "denied"
    action_type: str
    detail: str
    reason: str | None = None
    action_class: str | None = None  # normalized class for run_command


@dataclass
class CounterStats:
    total: int = 0
    approved: int = 0
    denied: int = 0
    errors: int = 0  # Not present in audit log; reserved for future
    last_timestamp: Optional[datetime] = None

    def update(self, ev: AuditEvent) -> None:
        self.total += 1
        if ev.status == "approved" or ev.status == "auto":
            self.approved += 1
        elif ev.status == "denied":
            self.denied += 1
        if self.last_timestamp is None or ev.ts > self.last_timestamp:
            self.last_timestamp = ev.ts

    def to_dict(self) -> Dict[str, object]:
        return {
            "total": self.total,
            "approved": self.approved,
            "denied": self.denied,
            "errors": self.errors,
            "last_timestamp": self.last_timestamp.isoformat(timespec="seconds") if self.last_timestamp else None,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_STATUS_NORMALIZE = {
    "auto": "auto",
    "auto    ": "auto",
    "approved": "approved",
    "denied": "denied",
    "denied  ": "denied",
}


def _extract_action_class(action_type: str, detail: str) -> Optional[str]:
    """Return a normalized action class for run_command; else None.

    Heuristics:
      - docker/systemctl → first two tokens (e.g., "docker restart")
      - Known destructive/config patterns seen in Judge → exact pattern class
      - Else: first token (e.g., "grep", "cat") or token pair if it carries meaning (e.g., "ufw allow")
    """
    if action_type != "run_command":
        return None

    cmd = detail.strip().lower()
    if not cmd:
        return None

    # Known dangerous/config patterns (mirror hal/judge.py ordering)
    destructive = [
        "rm -rf",
        "drop table",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",
    ]
    for p in destructive:
        if p in cmd:
            return p

    # docker/systemctl verbs
    parts = cmd.split()
    if len(parts) >= 2 and parts[0] in {"docker", "systemctl"}:
        return f"{parts[0]} {parts[1]}"

    # ufw allow/deny/grant
    if len(parts) >= 2 and parts[0] == "ufw":
        return f"ufw {parts[1]}"

    # redirect to /etc (config write) — captured in judge as "> /etc"
    if "> /etc" in cmd:
        return "> /etc"

    # Fallback: first token
    return parts[0] if parts else None


def _parse_line(line: str) -> Optional[AuditEvent]:
    # Expected segments separated by " | "; reason is optional at the end
    # Example: 2026-02-24T13:42:01 | tier=1 | approved | run_command    | systemctl restart vllm | planned restart
    parts = line.rstrip("\n").split(" | ")
    if len(parts) < 4:
        return None
    try:
        ts = datetime.fromisoformat(parts[0])
    except Exception:
        return None

    # tier=K
    tier_part = parts[1]
    if not tier_part.startswith("tier="):
        return None
    try:
        tier = int(tier_part.replace("tier=", "", 1))
    except ValueError:
        return None

    raw_status = parts[2].strip()
    status = _STATUS_NORMALIZE.get(raw_status, raw_status.strip())

    action_type = parts[3].strip()
    # When well-formed, parts[4] is detail; parts[5] (if present) is reason
    detail = parts[4].strip() if len(parts) >= 5 else ""
    reason = parts[5].strip() if len(parts) >= 6 else None

    action_class = _extract_action_class(action_type, detail)

    return AuditEvent(
        ts=ts,
        tier=tier,
        status=status,
        action_type=action_type,
        detail=detail,
        reason=reason,
        action_class=action_class,
    )


def load_audit_log(path: Path | str | None = None) -> Iterator[AuditEvent]:
    """Yield parsed AuditEvent entries from the audit log.

    If path is None, use env ORION_AUDIT_LOG or default ~/.orion/audit.log.
    Skips unreadable/malformed lines silently.
    """
    if path is None:
        env_path = os.getenv("ORION_AUDIT_LOG")
        if env_path:
            path = Path(env_path)
        else:
            path = Path.home() / ".orion" / "audit.log"
    else:
        path = Path(path)

    if not path.exists():
        return iter(())

    def _iter() -> Iterator[AuditEvent]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    ev = _parse_line(line)
                    if ev is not None:
                        yield ev
        except Exception:
            # On any unexpected IO error, return no events
            return

    return _iter()


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_stats(events: Iterable[AuditEvent]) -> Dict[str, Dict[str, Dict[str, object]]]:
    """Aggregate events into by_tool and by_action_class counters.

    Returns a dict with two maps: by_tool and by_action_class, each mapping key → stats dict.
    """
    by_tool: Dict[str, CounterStats] = {}
    by_action_class: Dict[str, CounterStats] = {}

    for ev in events:
        # By tool/action_type
        st = by_tool.setdefault(ev.action_type, CounterStats())
        st.update(ev)

        # By action class (only for run_command)
        if ev.action_class:
            stc = by_action_class.setdefault(ev.action_class, CounterStats())
            stc.update(ev)

    return {
        "by_tool": {k: v.to_dict() for k, v in by_tool.items()},
        "by_action_class": {k: v.to_dict() for k, v in by_action_class.items()},
    }


# ---------------------------------------------------------------------------
# Public API: get_action_stats
# ---------------------------------------------------------------------------

def get_action_stats(pattern: str, path: Path | str | None = None) -> Dict[str, object]:
    """Return aggregated stats for events matching a pattern.

    Pattern behavior:
      - Try to compile as regex (case-insensitive). If compilation fails, use case-insensitive substring.
      - Match against any of: action_type, detail, action_class (if present).

    Returns a dict suitable for JSON serialization, including a simple confidence = approved/total.
    """
    # Load all events once
    events = list(load_audit_log(path))

    # Prepare matcher
    regex: Optional[re.Pattern[str]] = None
    use_regex = True
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        use_regex = False
        needle = pattern.lower()

    def _matches(ev: AuditEvent) -> bool:
        haystacks = [ev.action_type, ev.detail]
        if ev.action_class:
            haystacks.append(ev.action_class)
        if use_regex and regex is not None:
            return any(regex.search(h or "") for h in haystacks)
        else:
            return any((needle in (h or "").lower()) for h in haystacks)

    matched = [ev for ev in events if _matches(ev)]

    # Aggregate matched subset
    agg = aggregate_stats(matched)
    total = 0
    approved = 0
    denied = 0
    last_ts: Optional[datetime] = None
    for ev in matched:
        total += 1
        if ev.status in ("approved", "auto"):
            approved += 1
        elif ev.status == "denied":
            denied += 1
        if last_ts is None or ev.ts > last_ts:
            last_ts = ev.ts

    confidence = (approved / total) if total > 0 else 0.0

    return {
        "pattern": pattern,
        "total": total,
        "approved": approved,
        "denied": denied,
        "errors": 0,
        "last_timestamp": last_ts.isoformat(timespec="seconds") if last_ts else None,
        "by_tool": agg["by_tool"],
        "by_action_class": agg["by_action_class"],
        "confidence": round(confidence, 4),
    }
