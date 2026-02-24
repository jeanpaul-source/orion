"""Tests for hal/trust_metrics.py — parsing, aggregation, and get_action_stats.

These tests are self-contained and do not touch the real ~/.orion/audit.log.
"""
from __future__ import annotations

import os
from pathlib import Path

import json

from hal.trust_metrics import load_audit_log, aggregate_stats, get_action_stats


_SAMPLE_LOG = """
2026-02-24T10:00:00 | tier=0 | auto     | search_kb     | prometheus port | quick lookup
2026-02-24T10:05:00 | tier=1 | approved | run_command    | docker restart grafana | restart service
2026-02-24T10:06:00 | tier=1 | denied   | run_command    | systemctl restart vllm | hold off
2026-02-24T10:07:00 | tier=0 | auto     | get_metrics    | 
2026-02-24T10:08:00 | tier=2 | approved | write_file     | /etc/some.conf | apply config
2026-02-24T10:09:00 | tier=1 | approved | run_command    | ufw allow 8080 | open port
2026-02-24T10:10:00 | tier=3 | denied   | run_command    | rm -rf /tmp/something | dangerous
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
    assert any(ev.status == "auto" and ev.action_type.strip() == "search_kb" for ev in events)
    assert any(ev.status == "approved" and ev.action_type.strip() == "run_command" for ev in events)
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

    # Minimal dispatcher path using hal.agent._dispatch
    from unittest.mock import MagicMock
    from hal.agent import _dispatch

    kb = MagicMock()
    prom = MagicMock()
    executor = MagicMock()
    judge = MagicMock()

    out = _dispatch("get_action_stats", {"action_pattern": "docker restart"}, executor, judge, kb, prom)
    data = json.loads(out)
    assert data["total"] == 1
    assert data["approved"] == 1
    assert "by_action_class" in data
