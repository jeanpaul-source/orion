"""Tests for hal/security.py — Falco, Osquery and traffic security workers.

Pure unit tests — executor and judge are always mocked.
No live SSH, no Falco daemon, no Osquery required.
Fixture outputs match the shapes returned by the real tools on the server.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from hal.security import get_host_connections, get_security_events

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _judge(approve: bool = True) -> MagicMock:
    j = MagicMock()
    j.approve.return_value = approve
    return j


def _executor(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    e = MagicMock()
    e.run.return_value = {"stdout": stdout, "returncode": returncode, "stderr": stderr}
    return e


# Real-shaped Falco event (non-noisy)
_FALCO_EVENT = {
    "time": "2026-02-26T12:00:00.000000000Z",
    "rule": "Write below etc",
    "priority": "WARNING",
    "output": "Warning Write below etc (proc=bash file=/etc/crontab)",
    "output_fields": {
        "proc.name": "bash",
        "fd.name": "/etc/crontab",
    },
}

# Known-noisy event — must be filtered by is_falco_noise()
_NOISE_EVENT = {
    "time": "2026-02-26T12:01:00.000000000Z",
    "rule": "Read sensitive file untrusted",
    "priority": "WARNING",
    "output": "pg_isready read /etc/shadow",
    "output_fields": {
        "proc.name": "pg_isready",
        "fd.name": "/etc/shadow",
    },
}


# ---------------------------------------------------------------------------
# Proof 1 — happy-path result shape
# ---------------------------------------------------------------------------


def test_get_security_events_returns_list():
    """get_security_events must return a list."""
    result = get_security_events(
        executor=_executor(stdout=json.dumps(_FALCO_EVENT)),
        judge=_judge(),
    )
    assert isinstance(result, list)


def test_get_security_events_result_has_expected_keys():
    """Each event dict must have exactly {time, rule, priority, proc_name, fd_name, output}."""
    events = get_security_events(
        executor=_executor(stdout=json.dumps(_FALCO_EVENT)),
        judge=_judge(),
    )
    assert len(events) == 1
    assert set(events[0].keys()) == {
        "time",
        "rule",
        "priority",
        "proc_name",
        "fd_name",
        "output",
    }


def test_get_security_events_values_mapped_correctly():
    """Event values must be extracted from the correct JSON fields."""
    event = get_security_events(
        executor=_executor(stdout=json.dumps(_FALCO_EVENT)),
        judge=_judge(),
    )[0]
    assert event["rule"] == "Write below etc"
    assert event["priority"] == "WARNING"
    assert event["proc_name"] == "bash"
    assert event["fd_name"] == "/etc/crontab"
    assert "2026-02-26" in event["time"]


def test_get_security_events_multiple_events_all_returned():
    """All non-noise events in the log must appear in output."""
    second = {**_FALCO_EVENT, "rule": "Outbound connection", "output": "bash outbound"}
    stdout = "\n".join([json.dumps(_FALCO_EVENT), json.dumps(second)])
    events = get_security_events(executor=_executor(stdout=stdout), judge=_judge())
    assert len(events) == 2


# ---------------------------------------------------------------------------
# Proof 2 — noise filtering
# ---------------------------------------------------------------------------


def test_get_security_events_noise_filtered_out():
    """pg_isready /etc/shadow events must be removed by the noise filter."""
    stdout = "\n".join([json.dumps(_NOISE_EVENT), json.dumps(_FALCO_EVENT)])
    events = get_security_events(executor=_executor(stdout=stdout), judge=_judge())
    assert len(events) == 1
    assert events[0]["rule"] == "Write below etc"


def test_get_security_events_all_noise_returns_empty_list():
    """If every event is noise, result must be []."""
    events = get_security_events(
        executor=_executor(stdout=json.dumps(_NOISE_EVENT)),
        judge=_judge(),
    )
    assert events == []


# ---------------------------------------------------------------------------
# Proof 3 — judge denial
# ---------------------------------------------------------------------------


def test_get_security_events_empty_when_judge_denies():
    """Judge denial must return [] without calling the executor."""
    exc = _executor()
    events = get_security_events(executor=exc, judge=_judge(approve=False))
    assert events == []
    exc.run.assert_not_called()


# ---------------------------------------------------------------------------
# Proof 4 — executor failure
# ---------------------------------------------------------------------------


def test_get_security_events_error_dict_on_nonzero_returncode():
    """returncode != 0 must produce a single-element list with an 'error' key."""
    events = get_security_events(
        executor=_executor(returncode=1, stderr="permission denied"),
        judge=_judge(),
    )
    assert len(events) == 1
    assert "error" in events[0]
    assert "permission denied" in events[0]["error"]


# ---------------------------------------------------------------------------
# Proof 5 — malformed / empty output
# ---------------------------------------------------------------------------


def test_get_security_events_skips_malformed_lines():
    """Non-JSON lines must be silently skipped."""
    stdout = "not json\n" + json.dumps(_FALCO_EVENT)
    events = get_security_events(executor=_executor(stdout=stdout), judge=_judge())
    assert len(events) == 1


def test_get_security_events_empty_stdout_returns_empty_list():
    """Empty log output must return []."""
    assert get_security_events(executor=_executor(stdout=""), judge=_judge()) == []


def test_get_security_events_blank_lines_skipped():
    """Lines with only whitespace must not cause errors."""
    stdout = "\n\n" + json.dumps(_FALCO_EVENT) + "\n\n"
    events = get_security_events(executor=_executor(stdout=stdout), judge=_judge())
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Proof 6 — get_host_connections shape
# ---------------------------------------------------------------------------


def _multi_executor(*results) -> MagicMock:
    """Executor that returns each result dict in sequence."""
    e = MagicMock()
    e.run.side_effect = list(results)
    return e


def test_get_host_connections_has_expected_top_level_keys():
    """get_host_connections must return a dict with listening/connections/arp keys."""
    listening = json.dumps(
        [{"name": "nginx", "port": 80, "address": "0.0.0.0", "protocol": 6}]
    )
    empty = json.dumps([])
    exc = _multi_executor(
        {"stdout": listening, "returncode": 0, "stderr": ""},
        {"stdout": empty, "returncode": 0, "stderr": ""},
        {"stdout": empty, "returncode": 0, "stderr": ""},
    )

    result = get_host_connections(executor=exc, judge=_judge())

    assert set(result.keys()) == {"listening", "connections", "arp"}


def test_get_host_connections_ignores_when_judge_denies():
    """Judge denial must return {} without calling executor."""
    exc = _executor()
    result = get_host_connections(executor=exc, judge=_judge(approve=False))
    assert result == {}
    exc.run.assert_not_called()


def test_get_host_connections_listening_ports_parsed():
    """Listening port data must be present in the 'listening' key as a list."""
    port_row = {"name": "prometheus", "port": 9091, "address": "0.0.0.0", "protocol": 6}
    listening = json.dumps([port_row])
    empty = json.dumps([])
    exc = _multi_executor(
        {"stdout": listening, "returncode": 0, "stderr": ""},
        {"stdout": empty, "returncode": 0, "stderr": ""},
        {"stdout": empty, "returncode": 0, "stderr": ""},
    )

    result = get_host_connections(executor=exc, judge=_judge())

    assert isinstance(result["listening"], list)
    assert result["listening"][0]["port"] == 9091


def test_get_security_events_output_field_defaults_on_missing_keys():
    """Events with absent output_fields sub-keys must default to empty string, not crash."""
    minimal_event = {
        "time": "2026-02-26T13:00:00Z",
        "rule": "Minimal Rule",
        "priority": "NOTICE",
        "output": "some output",
        "output_fields": {},  # proc.name and fd.name absent
    }
    events = get_security_events(
        executor=_executor(stdout=json.dumps(minimal_event)),
        judge=_judge(),
    )
    assert len(events) == 1
    assert events[0]["proc_name"] == ""
    assert events[0]["fd_name"] == ""


# ---------------------------------------------------------------------------
# FALCO_LOG path override via environment variable
# ---------------------------------------------------------------------------


def test_falco_log_path_env_var_override(monkeypatch):
    """FALCO_LOG_PATH env var overrides the default Falco log path."""
    custom_path = "/mnt/falco/events.json"
    monkeypatch.setenv("FALCO_LOG_PATH", custom_path)

    # Re-import to pick up the env var (module-level constant)
    import importlib

    import hal.security as sec

    importlib.reload(sec)
    try:
        assert custom_path == sec.FALCO_LOG

        # Verify the path is used in the executor call
        exc = _executor(stdout=json.dumps(_FALCO_EVENT))
        sec.get_security_events(executor=exc, judge=_judge())
        cmd = exc.run.call_args[0][0]
        assert custom_path in cmd
    finally:
        # Restore default so other tests aren't affected
        monkeypatch.delenv("FALCO_LOG_PATH", raising=False)
        importlib.reload(sec)


def test_falco_log_path_default():
    """Without FALCO_LOG_PATH env var, the default path is used."""
    from hal.security import FALCO_LOG

    assert FALCO_LOG == "/var/log/falco/events.json"
