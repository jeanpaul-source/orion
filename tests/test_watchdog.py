from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from hal import watchdog


class _FakePromClient:
    def __init__(self, _url: str, metrics: dict[str, float | None]):
        self._metrics = metrics

    def health(self) -> dict[str, float | None]:
        return self._metrics


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    metrics: dict[str, float | None],
    state: dict[str, str],
    checks: dict[str, str | None] | None = None,
) -> dict[str, object]:
    sent_metric: list[list[tuple[str, float, float, str, str]]] = []
    sent_simple: list[dict[str, object]] = []
    saved: dict[str, str] = {}

    monkeypatch.setattr(
        watchdog.cfg,
        "load",
        lambda: SimpleNamespace(prometheus_url="http://prom", ntfy_url="http://ntfy"),
    )
    monkeypatch.setattr(
        watchdog,
        "PrometheusClient",
        lambda url: _FakePromClient(url, metrics),
    )
    monkeypatch.setattr(watchdog, "_load_state", lambda: dict(state))
    monkeypatch.setattr(watchdog, "_save_state", lambda s: saved.update(dict(s)))
    monkeypatch.setattr(watchdog, "_log", lambda _msg: None)

    def _send_ntfy(_url: str, alerts: list[tuple[str, float, float, str, str]]) -> bool:
        sent_metric.append(alerts)
        return True

    def _send_ntfy_simple(
        _url: str,
        messages: list[str],
        urgency: str = "high",
        title: str = "Orion Alert — the-lab",
        tags: str = "warning,server",
    ) -> bool:
        sent_simple.append(
            {
                "messages": list(messages),
                "urgency": urgency,
                "title": title,
                "tags": tags,
            }
        )
        return True

    monkeypatch.setattr(watchdog, "_send_ntfy", _send_ntfy)
    monkeypatch.setattr(watchdog, "_send_ntfy_simple", _send_ntfy_simple)

    checks = checks or {}
    monkeypatch.setattr(watchdog, "_check_ntp", lambda **_kw: checks.get("ntp"))
    monkeypatch.setattr(
        watchdog,
        "_check_harvest",
        lambda **_kw: checks.get("harvest_lag"),
    )
    monkeypatch.setattr(
        watchdog,
        "_check_containers",
        lambda **_kw: checks.get("containers"),
    )
    monkeypatch.setattr(watchdog, "_check_falco", lambda **_kw: checks.get("falco"))
    monkeypatch.setattr(watchdog, "_check_trends", lambda **_kw: checks.get("trend"))
    monkeypatch.setattr(
        watchdog,
        "_check_component_health",
        lambda **_kw: checks.get("component_health"),
    )

    return {"sent_metric": sent_metric, "sent_simple": sent_simple, "saved": saved}


def test_metric_alert_fires_without_cooldown_and_persists_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _patch_common(
        monkeypatch,
        metrics={"cpu_pct": 90.0},
        state={},
    )

    watchdog.run()

    assert len(observed["sent_metric"]) == 1
    sent = observed["sent_metric"][0]
    assert len(sent) == 1
    assert sent[0][0] == "CPU usage"
    assert sent[0][1] == 90.0
    assert "cpu_pct" in observed["saved"]
    datetime.fromisoformat(observed["saved"]["cpu_pct"])


def test_metric_alert_is_suppressed_during_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    observed = _patch_common(
        monkeypatch,
        metrics={"cpu_pct": 90.0},
        state={"cpu_pct": now},
    )

    watchdog.run()

    assert observed["sent_metric"] == []
    assert observed["saved"]["cpu_pct"] == now


def test_metric_recovery_clears_cooldown_and_sends_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _patch_common(
        monkeypatch,
        metrics={"cpu_pct": 10.0},
        state={"cpu_pct": datetime.now().isoformat(timespec="seconds")},
    )

    watchdog.run()

    assert observed["sent_metric"] == []
    assert "cpu_pct" not in observed["saved"]
    assert len(observed["sent_simple"]) == 1
    resolved = observed["sent_simple"][0]
    assert resolved["urgency"] == "low"
    assert resolved["title"] == "Orion RESOLVED — the-lab"
    assert "CPU usage recovered" in resolved["messages"][0]


@pytest.mark.parametrize(
    ("key", "check_name", "message"),
    [
        ("ntp", "ntp", "NTP not synchronized"),
        ("harvest_lag", "harvest_lag", "Harvest stale"),
        ("containers", "containers", "Critical containers down"),
        ("falco", "falco", "2 Falco security events"),
    ],
)
def test_boolean_check_fires_suppresses_then_clears(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    check_name: str,
    message: str,
) -> None:
    checks = {"ntp": None, "harvest_lag": None, "containers": None, "falco": None}
    checks[check_name] = message

    first = _patch_common(
        monkeypatch,
        metrics={},
        state={},
        checks=checks,
    )
    watchdog.run()

    assert first["sent_metric"] == []
    assert len(first["sent_simple"]) == 1
    assert first["sent_simple"][0]["messages"] == [message]
    assert key in first["saved"]
    datetime.fromisoformat(first["saved"][key])

    suppress = _patch_common(
        monkeypatch,
        metrics={},
        state={key: datetime.now().isoformat(timespec="seconds")},
        checks=checks,
    )
    watchdog.run()

    assert suppress["sent_metric"] == []
    assert suppress["sent_simple"] == []
    assert key in suppress["saved"]

    clear_checks = {"ntp": None, "harvest_lag": None, "containers": None, "falco": None}
    clear = _patch_common(
        monkeypatch,
        metrics={},
        state={key: datetime.now().isoformat(timespec="seconds")},
        checks=clear_checks,
    )
    watchdog.run()

    assert key not in clear["saved"]
    assert len(clear["sent_simple"]) == 1
    resolved = clear["sent_simple"][0]
    assert resolved["messages"] == [f"{key} resolved"]
    assert resolved["urgency"] == "low"
    assert resolved["title"] == "Orion RESOLVED — the-lab"


# ---------------------------------------------------------------------------
# _check_trends unit tests
# ---------------------------------------------------------------------------


class _FakeTrendClient:
    """Minimal PrometheusClient stand-in that fakes trend() responses."""

    def __init__(
        self,
        trend_result: dict | None = None,
        raises: bool = False,
    ) -> None:
        self._trend_result = trend_result
        self._raises = raises

    def health(self) -> dict:
        return {}

    def trend(self, promql: str, window: str = "1h") -> dict | None:
        if self._raises:
            raise RuntimeError("prom unreachable")
        return self._trend_result


def _fake_config(**overrides: float) -> object:
    defaults = {
        "watchdog_disk_rate_pct_per_hour": 5.0,
        "watchdog_mem_rate_pct_per_hour": 5.0,
        "watchdog_swap_rate_pct_per_hour": 10.0,
        "watchdog_gpu_vram_rate_pct_per_hour": 5.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _stable_summary(delta_per_hour: float = 0.1) -> dict:
    return {
        "first": 50.0,
        "last": 50.1,
        "min": 50.0,
        "max": 50.1,
        "delta": 0.1,
        "delta_per_hour": delta_per_hour,
        "direction": "stable",
    }


def _rising_summary(delta_per_hour: float = 7.5) -> dict:
    return {
        "first": 50.0,
        "last": 57.5,
        "min": 50.0,
        "max": 57.5,
        "delta": 7.5,
        "delta_per_hour": delta_per_hour,
        "direction": "rising",
    }


def test_check_trends_stable_returns_none() -> None:
    prom = _FakeTrendClient(trend_result=_stable_summary())
    result = watchdog._check_trends(prom=prom, config=_fake_config())
    assert result is None


def test_check_trends_rising_above_threshold_fires() -> None:
    # delta_per_hour=7.5 > default threshold 5.0 → should fire
    prom = _FakeTrendClient(trend_result=_rising_summary(delta_per_hour=7.5))
    result = watchdog._check_trends(prom=prom, config=_fake_config())
    assert result is not None
    assert "trending toward threshold" in result
    assert "+7.5%/hr" in result


def test_check_trends_rising_below_threshold_no_alert() -> None:
    # delta_per_hour=2.0 < default threshold 5.0 → no alert
    prom = _FakeTrendClient(
        trend_result={
            **_rising_summary(delta_per_hour=2.0),
            "direction": "rising",
        }
    )
    result = watchdog._check_trends(prom=prom, config=_fake_config())
    assert result is None


def test_check_trends_falling_no_alert() -> None:
    prom = _FakeTrendClient(
        trend_result={
            "first": 60.0,
            "last": 52.0,
            "min": 52.0,
            "max": 60.0,
            "delta": -8.0,
            "delta_per_hour": -8.0,
            "direction": "falling",
        }
    )
    result = watchdog._check_trends(prom=prom, config=_fake_config())
    assert result is None


def test_check_trends_trend_returns_none_skips_metric() -> None:
    # trend() returning None means no data — should not crash or fire
    prom = _FakeTrendClient(trend_result=None)
    result = watchdog._check_trends(prom=prom, config=_fake_config())
    assert result is None


def test_check_trends_trend_raises_skips_metric() -> None:
    # trend() raising should be swallowed — no crash, no alert
    prom = _FakeTrendClient(raises=True)
    result = watchdog._check_trends(prom=prom, config=_fake_config())
    assert result is None


def test_check_trends_fires_through_run_with_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: run() fires trend alert, cooldown suppresses, resolves on clear."""
    trend_msg = "1 metric trending toward threshold:\nDisk /docker usage trending +7.5%/hr (threshold: 5%/hr)"

    # First run — no cooldown — should fire
    first = _patch_common(
        monkeypatch,
        metrics={},
        state={},
        checks={"trend": trend_msg},
    )
    watchdog.run()

    assert first["sent_metric"] == []
    assert len(first["sent_simple"]) == 1
    assert first["sent_simple"][0]["messages"] == [trend_msg]
    assert first["sent_simple"][0]["urgency"] == "high"
    assert "trend" in first["saved"]
    datetime.fromisoformat(first["saved"]["trend"])

    # Second run — in cooldown — should be suppressed
    suppress = _patch_common(
        monkeypatch,
        metrics={},
        state={"trend": datetime.now().isoformat(timespec="seconds")},
        checks={"trend": trend_msg},
    )
    watchdog.run()

    assert suppress["sent_simple"] == []
    assert "trend" in suppress["saved"]

    # Third run — trend cleared — should send resolved and remove state key
    clear = _patch_common(
        monkeypatch,
        metrics={},
        state={"trend": datetime.now().isoformat(timespec="seconds")},
        checks={"trend": None},
    )
    watchdog.run()

    assert "trend" not in clear["saved"]
    assert len(clear["sent_simple"]) == 1
    resolved = clear["sent_simple"][0]
    assert resolved["messages"] == ["trend resolved"]
    assert resolved["urgency"] == "low"
    assert resolved["title"] == "Orion RESOLVED — the-lab"


# ---------------------------------------------------------------------------
# Phase B4 — Component health check integration
# ---------------------------------------------------------------------------


def test_check_component_health_returns_none_when_all_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_check_component_health returns None when all components are ok."""
    from hal.healthcheck import ComponentHealth

    fake_results = [
        ComponentHealth(name="vllm", status="ok", detail="healthy", latency_ms=10),
        ComponentHealth(name="ollama", status="ok", detail="healthy", latency_ms=5),
    ]
    monkeypatch.setattr("hal.healthcheck.run_all_checks", lambda config: fake_results)

    result = watchdog._check_component_health(
        config=SimpleNamespace(), state={}, prom=None
    )
    assert result is None


def test_check_component_health_returns_alert_when_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_check_component_health returns alert message for degraded components."""
    from hal.healthcheck import ComponentHealth

    fake_results = [
        ComponentHealth(name="vllm", status="ok", detail="healthy", latency_ms=10),
        ComponentHealth(
            name="ollama", status="degraded", detail="model missing", latency_ms=5
        ),
        ComponentHealth(
            name="pgvector", status="down", detail="connection refused", latency_ms=0
        ),
    ]
    monkeypatch.setattr("hal.healthcheck.run_all_checks", lambda config: fake_results)
    monkeypatch.setattr(watchdog, "_attempt_recovery", lambda *a, **kw: None)

    result = watchdog._check_component_health(
        config=SimpleNamespace(), state={}, prom=None
    )
    assert result is not None
    assert "2 components unhealthy" in result
    assert "ollama: degraded" in result
    assert "pgvector: down" in result


def test_check_component_health_returns_none_when_config_is_none() -> None:
    """_check_component_health returns None when config is None (no-op)."""
    result = watchdog._check_component_health(config=None, state={}, prom=None)
    assert result is None


def test_check_component_health_swallows_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_check_component_health catches all exceptions and returns None."""
    monkeypatch.setattr(
        "hal.healthcheck.run_all_checks",
        lambda config: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = watchdog._check_component_health(
        config=SimpleNamespace(), state={}, prom=None
    )
    assert result is None


def test_component_health_fires_through_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: component_health alert fires through run() when unhealthy."""
    alert_msg = "1 component unhealthy:\nvllm: down — connection refused"

    observed = _patch_common(
        monkeypatch,
        metrics={},
        state={},
        checks={"component_health": alert_msg},
    )
    watchdog.run()

    assert len(observed["sent_simple"]) == 1
    assert observed["sent_simple"][0]["messages"] == [alert_msg]
    assert observed["sent_simple"][0]["urgency"] == "high"
    assert "component_health" in observed["saved"]


# ---------------------------------------------------------------------------
# C3 — Watchdog auto-recovery via playbooks
# ---------------------------------------------------------------------------


class TestWatchdogJudge:
    """Test WatchdogJudge auto-approval behavior."""

    def test_approves_tier_0(self, tmp_path: pytest.TempPathFactory) -> None:
        audit = tmp_path / "audit.log"  # type: ignore[operator]
        judge = watchdog.WatchdogJudge(audit_log=audit)
        assert judge.approve("search_kb", "test query") is True

    def test_approves_tier_1_via_trust(self, tmp_path: pytest.TempPathFactory) -> None:
        """Tier 1 actions are denied because _request_approval returns False."""
        audit = tmp_path / "audit.log"  # type: ignore[operator]
        judge = watchdog.WatchdogJudge(audit_log=audit)
        # docker restart is tier 1, _request_approval returns False
        assert judge.approve("run_command", "docker restart pgvector-kb") is False

    def test_denies_tier_2(self, tmp_path: pytest.TempPathFactory) -> None:
        audit = tmp_path / "audit.log"  # type: ignore[operator]
        judge = watchdog.WatchdogJudge(audit_log=audit)
        assert judge.approve("run_command", "sudo systemctl restart ollama") is False


class TestAttemptRecovery:
    """Test _attempt_recovery with mocked playbook execution."""

    def test_no_playbook_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(watchdog, "get_playbook", lambda *a: None)
        config = SimpleNamespace(lab_host="localhost", lab_user="jp", ntfy_url="")
        result = watchdog._attempt_recovery("nonexistent", "down", config)
        assert result is None

    def test_high_tier_playbook_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hal.playbooks import RecoveryPlaybook, RecoveryStep

        pb = RecoveryPlaybook(
            name="restart_ollama",
            component="Ollama",
            trigger="down",
            description="test",
            judge_tier=2,
            max_attempts_per_hour=2,
            steps=(
                RecoveryStep(
                    description="restart",
                    command="sudo systemctl restart ollama",
                    verify_command="systemctl is-active ollama",
                    verify_expect="active",
                ),
            ),
        )
        monkeypatch.setattr(watchdog, "get_playbook", lambda *a: pb)
        monkeypatch.setattr(watchdog, "_log", lambda _msg: None)
        config = SimpleNamespace(lab_host="localhost", lab_user="jp", ntfy_url="")
        result = watchdog._attempt_recovery("Ollama", "down", config)
        assert result is not None
        assert "tier 2" in result

    def test_successful_recovery_sends_notification(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from hal.playbooks import PlaybookResult, RecoveryPlaybook, RecoveryStep

        pb = RecoveryPlaybook(
            name="restart_pgvector",
            component="pgvector",
            trigger="down",
            description="test",
            judge_tier=1,
            max_attempts_per_hour=3,
            steps=(
                RecoveryStep(
                    description="restart",
                    command="docker restart pgvector-kb",
                    verify_command="docker ps --filter name=pgvector-kb",
                    verify_expect="pgvector-kb:Up",
                ),
            ),
        )

        sent: list[dict] = []
        monkeypatch.setattr(watchdog, "get_playbook", lambda *a: pb)
        monkeypatch.setattr(watchdog, "_log", lambda _msg: None)
        monkeypatch.setattr(
            watchdog,
            "execute_playbook",
            lambda *a, **kw: PlaybookResult(
                success=True,
                steps_completed=1,
                detail="All 1 steps completed successfully",
                playbook_name="restart_pgvector",
            ),
        )
        monkeypatch.setattr(
            watchdog,
            "_send_ntfy_simple",
            lambda url, messages, **kw: (
                sent.append({"messages": messages, **kw}) or True
            ),
        )
        # Patch SSHExecutor and WatchdogJudge constructors
        monkeypatch.setattr(watchdog, "SSHExecutor", lambda *a: None)
        monkeypatch.setattr(watchdog, "WatchdogJudge", lambda **kw: None)

        config = SimpleNamespace(
            lab_host="localhost", lab_user="jp", ntfy_url="http://ntfy"
        )
        result = watchdog._attempt_recovery("pgvector", "down", config)
        assert result is not None
        assert "RECOVERED" in result
        assert len(sent) == 1
        assert "RECOVERED" in sent[0].get("title", "")

    def test_failed_recovery_sends_failure_notification(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from hal.playbooks import PlaybookResult, RecoveryPlaybook, RecoveryStep

        pb = RecoveryPlaybook(
            name="restart_pgvector",
            component="pgvector",
            trigger="down",
            description="test",
            judge_tier=1,
            max_attempts_per_hour=3,
            steps=(
                RecoveryStep(
                    description="restart",
                    command="docker restart pgvector-kb",
                    verify_command="docker ps --filter name=pgvector-kb",
                    verify_expect="pgvector-kb:Up",
                ),
            ),
        )

        sent: list[dict] = []
        monkeypatch.setattr(watchdog, "get_playbook", lambda *a: pb)
        monkeypatch.setattr(watchdog, "_log", lambda _msg: None)
        monkeypatch.setattr(
            watchdog,
            "execute_playbook",
            lambda *a, **kw: PlaybookResult(
                success=False,
                steps_completed=0,
                detail="container not found",
                playbook_name="restart_pgvector",
            ),
        )
        monkeypatch.setattr(
            watchdog,
            "_send_ntfy_simple",
            lambda url, messages, **kw: (
                sent.append({"messages": messages, **kw}) or True
            ),
        )
        monkeypatch.setattr(watchdog, "SSHExecutor", lambda *a: None)
        monkeypatch.setattr(watchdog, "WatchdogJudge", lambda **kw: None)

        config = SimpleNamespace(
            lab_host="localhost", lab_user="jp", ntfy_url="http://ntfy"
        )
        result = watchdog._attempt_recovery("pgvector", "down", config)
        assert result is not None
        assert "RECOVERY FAILED" in result
        assert len(sent) == 1
        assert "FAILED" in sent[0].get("title", "")


def test_check_component_health_with_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_check_component_health calls _attempt_recovery and includes messages."""
    from hal.healthcheck import ComponentHealth

    fake_results = [
        ComponentHealth(
            name="pgvector", status="down", detail="connection refused", latency_ms=0
        ),
    ]
    monkeypatch.setattr("hal.healthcheck.run_all_checks", lambda config: fake_results)
    monkeypatch.setattr(
        watchdog,
        "_attempt_recovery",
        lambda name, status, config: f"RECOVERED {name}: restarted",
    )

    result = watchdog._check_component_health(
        config=SimpleNamespace(), state={}, prom=None
    )
    assert result is not None
    assert "1 component" in result
    assert "Recovery actions" in result
    assert "RECOVERED pgvector" in result
