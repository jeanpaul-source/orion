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
