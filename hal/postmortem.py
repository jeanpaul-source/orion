"""Post-incident evidence gathering for the /postmortem slash command.
# why locked: Layer 3 — depends on security and trust_metrics (both Layer 3)

Provides a single pure function, gather_postmortem_context(), that collects
audit log events, Prometheus metric snapshots/trends, and Falco security events
from the given window and formats them as a single context block for the agent
loop.

No LLM calls are made here.  All I/O errors are caught and produce an
"unavailable" note rather than raising.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from hal.executor import SSHExecutor
from hal.judge import Judge
from hal.prometheus import PrometheusClient
from hal.security import (
    get_security_events,
)
from hal.trust_metrics import (
    load_audit_log,
)

_log = logging.getLogger(__name__)

# PromQL expressions for the three trend metrics (mirrors PrometheusClient.health())
_CPU_PROMQL = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
_MEM_PROMQL = "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100"
_DISK_DOCKER_PROMQL = (
    '(1 - node_filesystem_avail_bytes{mountpoint="/docker"}'
    ' / node_filesystem_size_bytes{mountpoint="/docker"}) * 100'
)


def _format_ts(dt: datetime) -> str:
    """Return a compact ISO timestamp string (no microseconds, UTC-normalised)."""
    try:
        # Normalise timezone-aware datetimes to UTC; keep naive datetimes as-is.
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return str(dt)


def _audit_section(window_hours: int) -> str:
    """Return a formatted audit-log timeline for the window.

    Includes only tier > 0 actions (non-trivial) and any denied actions
    (which are always noteworthy regardless of tier).
    """
    cutoff = time.time() - window_hours * 3600
    lines: list[str] = []
    try:
        for ev in load_audit_log():
            # Compare via POSIX timestamp to sidestep naive/aware mismatch.
            try:
                ev_ts = ev.ts.timestamp()
            except Exception:
                _log.debug(
                    "Skipping audit event with unparseable timestamp", exc_info=True
                )
                continue
            if ev_ts < cutoff:
                continue
            # Include: elevated-tier actions (tier >= 1) or any denial.
            if ev.tier <= 0 and ev.status != "denied":
                continue
            tag = ""
            if ev.status == "denied":
                tag = " [DENIED]"
            elif ev.status == "approved":
                tag = " [approved]"
            detail = f" — {ev.detail}" if ev.detail else ""
            reason = f" ({ev.reason})" if ev.reason else ""
            lines.append(
                f"  {_format_ts(ev.ts)}  tier={ev.tier}  {ev.action_type}"
                f"{detail}{reason}{tag}"
            )
    except Exception as exc:
        return f"[audit log unavailable: {exc}]"

    if not lines:
        return f"[no significant audit events in the last {window_hours}h]"
    return "\n".join(lines)


def _prometheus_section(window_hours: int, prom: PrometheusClient) -> str:
    """Return a brief Prometheus snapshot + trend summary."""
    parts: list[str] = []

    # Current snapshot
    try:
        h = prom.health()
        snap_lines = []
        for key, val in h.items():
            snap_lines.append(
                f"  {key:<20} {val if val is not None else 'unavailable'}"
            )
        parts.append("Current snapshot:\n" + "\n".join(snap_lines))
    except Exception as exc:
        parts.append(f"Current snapshot: unavailable ({exc})")

    # Trends for three key metrics
    window_str = f"{window_hours}h"
    trend_metrics = [
        ("cpu_pct", _CPU_PROMQL),
        ("mem_pct", _MEM_PROMQL),
        ("disk_docker_pct", _DISK_DOCKER_PROMQL),
    ]
    trend_lines: list[str] = []
    for label, promql in trend_metrics:
        try:
            t = prom.trend(promql, window=window_str)
            if t is None:
                trend_lines.append(f"  {label:<20} unavailable (insufficient data)")
            else:
                trend_lines.append(
                    f"  {label:<20} {t['direction']:8}  "
                    f"first={t['first']}  last={t['last']}  "
                    f"delta={t['delta']:+.2f}  Δ/hr={t['delta_per_hour']:+.2f}"
                )
        except Exception as exc:
            trend_lines.append(f"  {label:<20} unavailable ({exc})")
    parts.append(f"Trends over {window_str}:\n" + "\n".join(trend_lines))

    return "\n\n".join(parts)


def _falco_section(executor: SSHExecutor, judge: Judge) -> str:
    """Return a formatted list of recent Falco security events."""
    try:
        events = get_security_events(executor, judge, n=50, reason="postmortem")
    except Exception as exc:
        return f"[Falco unavailable: {exc}]"

    if not events:
        return "[no Falco events]"

    # Check for a top-level error dict (returned by get_security_events on failure)
    if len(events) == 1 and "error" in events[0]:
        return f"[Falco unavailable: {events[0]['error']}]"

    lines: list[str] = []
    for ev in events:
        ts = ev.get("time", "")[:19]  # trim sub-second precision
        rule = ev.get("rule", "?")
        priority = ev.get("priority", "")
        proc = ev.get("proc_name", "")
        fd = ev.get("fd_name", "")
        detail = f"  proc={proc}" if proc else ""
        detail += f"  fd={fd}" if fd else ""
        lines.append(f"  {ts}  [{priority}]  {rule}{detail}")
    return "\n".join(lines)


def gather_postmortem_context(
    description: str,
    window_hours: int,
    prom: PrometheusClient,
    executor: SSHExecutor,
    judge: Judge,
) -> str:
    """Collect and format three evidence layers for a post-mortem.

    Parameters
    ----------
    description:
        The incident description provided by the operator.
    window_hours:
        How far back to look in the audit log and Prometheus trends.
    prom:
        Live PrometheusClient instance.
    executor:
        SSHExecutor connected to the lab host.
    judge:
        Judge instance (required by get_security_events).

    Returns
    -------
    A single formatted string suitable for injection into an agent query.
    No LLM calls are made here.
    """
    audit = _audit_section(window_hours)
    prom_text = _prometheus_section(window_hours, prom)
    falco = _falco_section(executor, judge)

    return (
        f"=== POST-INCIDENT EVIDENCE ===\n"
        f"Incident: {description}\n"
        f"Window: last {window_hours}h\n\n"
        f"── AUDIT LOG ──────────────────────────────────────────\n"
        f"{audit}\n\n"
        f"── PROMETHEUS ─────────────────────────────────────────\n"
        f"{prom_text}\n\n"
        f"── FALCO SECURITY EVENTS ──────────────────────────────\n"
        f"{falco}\n"
    )
