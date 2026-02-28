"""Offline tests for hal/postmortem.py and the /postmortem REPL handler.

All tests mock external I/O (audit log, Prometheus, Falco) so no live services
are needed.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import hal.postmortem as pm
from hal.postmortem import (
    _audit_section,
    _falco_section,
    _prometheus_section,
    gather_postmortem_context,
)
from hal.trust_metrics import AuditEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    ts_posix: float,
    tier: int = 1,
    status: str = "approved",
    action_type: str = "run_command",
    detail: str = "docker restart grafana",
    reason: str = "fix",
) -> AuditEvent:
    return AuditEvent(
        ts=datetime.fromtimestamp(ts_posix, tz=timezone.utc),
        tier=tier,
        status=status,
        action_type=action_type,
        detail=detail,
        reason=reason,
    )


def _stub_prom(*, health=None, trend=None):
    prom = MagicMock()
    prom.health.return_value = health or {
        "cpu_pct": 12.3,
        "mem_pct": 55.0,
        "disk_docker_pct": 70.0,
    }
    prom.trend.return_value = trend or {
        "first": 65.0,
        "last": 70.0,
        "min": 64.0,
        "max": 71.0,
        "delta": 5.0,
        "delta_per_hour": 2.5,
        "direction": "rising",
    }
    return prom


def _stub_executor_judge():
    executor = MagicMock()
    judge = MagicMock()
    judge.approve.return_value = True
    return executor, judge


# ---------------------------------------------------------------------------
# 1. gather_postmortem_context returns a non-empty string with all sections
# ---------------------------------------------------------------------------


def test_gather_returns_nonempty_string_with_description():
    now = time.time()
    in_window_event = _make_event(now - 30 * 60)  # 30 min ago, tier 1

    executor, judge = _stub_executor_judge()
    prom = _stub_prom()

    falco_event = {
        "time": "2026-02-26T10:00:00.000000000+0000",
        "rule": "Write below etc",
        "priority": "WARNING",
        "proc_name": "bash",
        "fd_name": "/etc/cron.d/something",
        "output": "test output",
    }

    with (
        patch.object(pm, "load_audit_log", return_value=iter([in_window_event])),
        patch.object(pm, "get_security_events", return_value=[falco_event]),
    ):
        result = gather_postmortem_context(
            description="disk full on /docker",
            window_hours=2,
            prom=prom,
            executor=executor,
            judge=judge,
        )

    assert isinstance(result, str)
    assert len(result) > 0
    assert "disk full on /docker" in result
    assert "AUDIT LOG" in result
    assert "PROMETHEUS" in result
    assert "FALCO" in result


# ---------------------------------------------------------------------------
# 2. Audit window excludes events older than window_hours
# ---------------------------------------------------------------------------


def test_audit_window_excludes_old_events():
    now = 1_000_000.0  # fixed fake epoch

    old_event = _make_event(now - 3 * 3600)  # 3h ago — outside 2h window
    new_event = _make_event(
        now - 30 * 60, detail="systemctl restart grafana"
    )  # 30 min ago

    with (
        patch.object(pm.time, "time", return_value=now),
        patch.object(pm, "load_audit_log", return_value=iter([old_event, new_event])),
    ):
        result = _audit_section(2)

    assert "systemctl restart grafana" in result
    assert "docker restart grafana" not in result  # old event detail


# ---------------------------------------------------------------------------
# 3. Tier-0 denial is included despite tier being 0
# ---------------------------------------------------------------------------


def test_audit_window_includes_tier0_denial():
    now = 1_000_000.0

    tier0_denial = _make_event(
        now - 10 * 60,
        tier=0,
        status="denied",
        action_type="web_search",
        detail="sensitive query",
    )
    tier0_auto = _make_event(
        now - 5 * 60,
        tier=0,
        status="auto",
        action_type="search_kb",
        detail="normal lookup",
    )

    with (
        patch.object(pm.time, "time", return_value=now),
        patch.object(
            pm, "load_audit_log", return_value=iter([tier0_denial, tier0_auto])
        ),
    ):
        result = _audit_section(2)

    # Denial must appear
    assert "sensitive query" in result
    assert "[DENIED]" in result
    # Auto tier-0 must be excluded
    assert "normal lookup" not in result


# ---------------------------------------------------------------------------
# 4. Prometheus unreachable is handled gracefully
# ---------------------------------------------------------------------------


def test_prometheus_unavailable_graceful():
    prom = MagicMock()
    prom.health.side_effect = RuntimeError("connection refused")

    result = _prometheus_section(2, prom)

    assert "unavailable" in result
    # Trend calls may or may not fire; either way, no exception is raised


# ---------------------------------------------------------------------------
# 5. Falco unreachable is handled gracefully
# ---------------------------------------------------------------------------


def test_falco_unavailable_graceful():
    executor, judge = _stub_executor_judge()

    with patch.object(
        pm, "get_security_events", side_effect=RuntimeError("SSH failed")
    ):
        result = _falco_section(executor, judge)

    assert "unavailable" in result.lower()


# ---------------------------------------------------------------------------
# 6. Falco returning an error dict is reported cleanly
# ---------------------------------------------------------------------------


def test_falco_error_dict_reported_cleanly():
    executor, judge = _stub_executor_judge()

    with patch.object(
        pm,
        "get_security_events",
        return_value=[{"error": "Falco log read failed: no such file"}],
    ):
        result = _falco_section(executor, judge)

    assert "unavailable" in result.lower()
    assert "Falco log read failed" in result
