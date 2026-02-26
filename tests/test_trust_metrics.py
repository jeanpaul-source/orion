"""Tests for hal/trust_metrics.py — parsing, aggregation, and get_action_stats.

These tests are self-contained and do not touch the real ~/.orion/audit.log.
"""

from __future__ import annotations

import json
from pathlib import Path

from hal.trust_metrics import aggregate_stats, get_action_stats, load_audit_log

# Original sample log in legacy pipe format is now replaced with JSON equivalents.
# The legacy parser (_parse_legacy_line) was deleted in N7 because the JSON format
# is the only format written by hal/judge.py today.
_SAMPLE_LOG = """
{"ts": "2026-02-24T10:00:00", "tier": 0, "status": "auto", "action": "search_kb", "detail": "prometheus port", "reason": "quick lookup"}
{"ts": "2026-02-24T10:05:00", "tier": 1, "status": "approved", "action": "run_command", "detail": "docker restart grafana", "reason": "restart service"}
{"ts": "2026-02-24T10:06:00", "tier": 1, "status": "denied", "action": "run_command", "detail": "systemctl restart vllm", "reason": "hold off"}
{"ts": "2026-02-24T10:07:00", "tier": 0, "status": "auto", "action": "get_metrics", "detail": ""}
{"ts": "2026-02-24T10:08:00", "tier": 2, "status": "approved", "action": "write_file", "detail": "/etc/some.conf", "reason": "apply config"}
{"ts": "2026-02-24T10:09:00", "tier": 1, "status": "approved", "action": "run_command", "detail": "ufw allow 8080", "reason": "open port"}
{"ts": "2026-02-24T10:10:00", "tier": 3, "status": "denied", "action": "run_command", "detail": "rm -rf /tmp/something", "reason": "dangerous"}
""".strip()

_SAMPLE_JSON_LOG = """
{"ts": "2026-02-25T14:00:00+00:00", "tier": 0, "status": "auto", "action": "search_kb", "detail": "pgvector port", "reason": "quick lookup"}
{"ts": "2026-02-25T14:05:00+00:00", "tier": 1, "status": "approved", "action": "run_command", "detail": "docker restart grafana", "reason": "restart service"}
{"ts": "2026-02-25T14:06:00+00:00", "tier": 1, "status": "denied", "action": "run_command", "detail": "systemctl restart vllm", "reason": "hold off"}
{"ts": "2026-02-25T14:07:00+00:00", "tier": 0, "status": "auto", "action": "get_metrics", "detail": ""}
{"ts": "2026-02-25T14:08:00+00:00", "tier": 2, "status": "approved", "action": "write_file", "detail": "/etc/some.conf", "reason": "apply config"}
{"ts": "2026-02-25T14:09:00+00:00", "tier": 0, "status": "auto", "action": "web_search", "detail": "prometheus latest version"}
{"ts": "2026-02-25T14:10:00+00:00", "tier": 3, "status": "denied", "action": "run_command", "detail": "rm -rf /tmp/something", "reason": "dangerous"}
""".strip()


def _write_temp_audit(tmp_path: Path) -> Path:
    p = tmp_path / "audit.log"
    p.write_text(_SAMPLE_LOG + "\n", encoding="utf-8")
    return p


def test_load_audit_log_parses_events(tmp_path):
    p = _write_temp_audit(tmp_path)
    events = list(load_audit_log(p))
    assert len(events) == 7
    # Check one auto and one approved/denied
    assert any(
        ev.status == "auto" and ev.action_type.strip() == "search_kb" for ev in events
    )
    assert any(
        ev.status == "approved" and ev.action_type.strip() == "run_command"
        for ev in events
    )
    assert any(ev.status == "denied" and ev.tier == 3 for ev in events)
    # Action class extraction
    classes = {ev.action_class for ev in events if ev.action_class}
    assert "docker restart" in classes
    assert "systemctl restart" in classes
    assert "ufw allow" in classes
    assert "rm -rf" in classes


def test_aggregate_stats_counts_and_last_timestamp(tmp_path):
    p = _write_temp_audit(tmp_path)
    events = list(load_audit_log(p))
    agg = aggregate_stats(events)
    by_tool = agg["by_tool"]
    by_class = agg["by_action_class"]

    assert by_tool["search_kb"]["total"] == 1
    assert by_tool["get_metrics"]["approved"] == 1  # auto counts as approved
    assert by_tool["run_command"]["total"] == 4

    # last_timestamp present and ISO string
    assert isinstance(by_tool["write_file"]["last_timestamp"], str)

    # action class rollups
    assert by_class["docker restart"]["approved"] == 1
    assert by_class["systemctl restart"]["denied"] == 1
    assert by_class["ufw allow"]["approved"] == 1
    assert by_class["rm -rf"]["denied"] == 1


def test_get_action_stats_regex_and_substring(tmp_path, monkeypatch):
    p = _write_temp_audit(tmp_path)
    monkeypatch.setenv("ORION_AUDIT_LOG", str(p))

    # Regex: match any restart (docker or systemctl)
    stats = get_action_stats(r"(docker|systemctl)\s+restart")
    assert stats["total"] == 2
    assert stats["approved"] == 1
    assert stats["denied"] == 1
    assert 0.0 < stats["confidence"] < 1.0

    # Substring fallback: no regex meta
    stats2 = get_action_stats("ufw allow")
    assert stats2["total"] == 1
    assert stats2["approved"] == 1
    assert stats2["confidence"] == 1.0

    # No matches
    stats3 = get_action_stats("nonexistent pattern")
    assert stats3["total"] == 0
    assert stats3["approved"] == 0
    assert stats3["confidence"] == 0.0


def test_dispatch_integration_via_agent_tool(tmp_path, monkeypatch):
    # Create temp audit log and point env to it
    p = _write_temp_audit(tmp_path)
    monkeypatch.setenv("ORION_AUDIT_LOG", str(p))

    # Minimal dispatcher path using hal.tools.dispatch_tool
    from unittest.mock import MagicMock

    from hal.tools import ToolContext, dispatch_tool

    kb = MagicMock()
    prom = MagicMock()
    executor = MagicMock()
    judge = MagicMock()

    out = dispatch_tool(
        "get_action_stats",
        {"action_pattern": "docker restart"},
        ToolContext(executor=executor, judge=judge, kb=kb, prom=prom),
    )
    data = json.loads(out)
    assert data["total"] == 1
    assert data["approved"] == 1
    assert "by_action_class" in data


# ---------------------------------------------------------------------------
# JSON audit format tests (F-17)
# ---------------------------------------------------------------------------


def _write_json_audit(tmp_path: Path) -> Path:
    p = tmp_path / "audit_json.log"
    p.write_text(_SAMPLE_JSON_LOG + "\n", encoding="utf-8")
    return p


def test_json_log_parses_all_events(tmp_path):
    p = _write_json_audit(tmp_path)
    events = list(load_audit_log(p))
    assert len(events) == 7


def test_json_log_status_values(tmp_path):
    p = _write_json_audit(tmp_path)
    events = list(load_audit_log(p))
    statuses = {ev.action_type: ev.status for ev in events}
    assert statuses["search_kb"] == "auto"
    assert statuses["write_file"] == "approved"
    assert statuses["web_search"] == "auto"


def test_json_log_tier_values(tmp_path):
    p = _write_json_audit(tmp_path)
    events = list(load_audit_log(p))
    tiers = {
        ev.action_type: ev.tier for ev in events if ev.action_type != "run_command"
    }
    assert tiers["search_kb"] == 0
    assert tiers["write_file"] == 2
    assert tiers["web_search"] == 0


def test_json_log_action_class_extraction(tmp_path):
    p = _write_json_audit(tmp_path)
    events = list(load_audit_log(p))
    classes = {ev.action_class for ev in events if ev.action_class}
    assert "docker restart" in classes
    assert "systemctl restart" in classes
    assert "rm -rf" in classes


def test_json_log_reason_preserved(tmp_path):
    p = _write_json_audit(tmp_path)
    events = list(load_audit_log(p))
    search_ev = [ev for ev in events if ev.action_type == "search_kb"][0]
    assert search_ev.reason == "quick lookup"


def test_json_log_aggregation(tmp_path):
    p = _write_json_audit(tmp_path)
    events = list(load_audit_log(p))
    agg = aggregate_stats(events)
    by_tool = agg["by_tool"]
    assert by_tool["run_command"]["total"] == 3


def test_json_log_get_action_stats(tmp_path, monkeypatch):
    p = _write_json_audit(tmp_path)
    monkeypatch.setenv("ORION_AUDIT_LOG", str(p))
    stats = get_action_stats("docker restart")
    assert stats["total"] == 1
    assert stats["approved"] == 1


def test_json_log_missing_fields_skipped(tmp_path):
    """Lines with missing required fields should be silently skipped."""
    p = tmp_path / "bad.log"
    p.write_text(
        '{"tier": 0, "status": "auto", "action": "get_metrics"}\n'  # missing ts
        '{"ts": "2026-02-25T14:00:00+00:00", "status": "auto", "action": "get_metrics"}\n'  # missing tier
        '{"ts": "2026-02-25T14:00:00+00:00", "tier": 0, "action": "get_metrics"}\n'  # missing status
        '{"ts": "2026-02-25T14:00:00+00:00", "tier": 0, "status": "auto"}\n'  # missing action
        '{"ts": "2026-02-25T14:00:00+00:00", "tier": 0, "status": "auto", "action": "get_metrics"}\n',  # valid
        encoding="utf-8",
    )
    events = list(load_audit_log(p))
    assert len(events) == 1


def test_mixed_json_and_legacy_log_legacy_lines_skipped(tmp_path):
    """Legacy pipe-delimited lines are silently skipped (parser only handles JSON)."""
    p = tmp_path / "mixed.log"
    p.write_text(
        "2026-02-24T10:00:00 | tier=0 | auto     | search_kb     | test | reason\n"
        '{"ts": "2026-02-25T14:00:00+00:00", "tier": 0, "status": "auto", "action": "get_metrics", "detail": ""}\n',
        encoding="utf-8",
    )
    events = list(load_audit_log(p))
    # Legacy line is silently skipped; only the JSON line is parsed
    assert len(events) == 1
    assert events[0].action_type == "get_metrics"
