"""Offline tests for hal/prometheus.py metric accumulation and flushing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import hal.prometheus as prom


@pytest.fixture(autouse=True)
def _reset_metric_state() -> None:
    prom._counters.clear()
    prom._gauges.clear()


def test_flush_metrics_noop_without_pushgateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def _fake_post(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(status_code=202)

    monkeypatch.delenv("PROM_PUSHGATEWAY", raising=False)
    monkeypatch.setattr(prom.requests, "post", _fake_post)

    prom.Counter("hal_events_total", labels=("intent",)).inc(intent="health")
    prom.flush_metrics()

    assert calls == []


def test_flush_metrics_pushes_counters_and_latest_histogram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pushed: dict[str, str] = {}

    def _fake_post(url, data, timeout):
        pushed["url"] = url
        pushed["data"] = data
        pushed["timeout"] = str(timeout)
        return SimpleNamespace(status_code=202)

    monkeypatch.setenv("PROM_PUSHGATEWAY", "http://pushgw:9092")
    monkeypatch.setenv("HAL_INSTANCE", "test-instance")
    monkeypatch.setattr(prom.requests, "post", _fake_post)

    counter = prom.Counter("hal_requests_total", labels=("endpoint", "outcome"))
    counter.inc(endpoint="chat", outcome="ok")
    counter.inc(endpoint="chat", outcome="ok")

    hist = prom.Histogram("hal_latency_seconds", labels=("endpoint",))
    hist.observe(0.11, endpoint="chat")
    hist.observe(0.42, endpoint="chat")

    prom.flush_metrics()

    assert pushed["url"] == "http://pushgw:9092/metrics/job/hal/instance/test-instance"
    assert pushed["timeout"] == "2"
    assert 'hal_requests_total{endpoint="chat",outcome="ok"} 2' in pushed["data"]
    assert 'hal_latency_seconds{endpoint="chat"} 0.42' in pushed["data"]


def test_flush_metrics_swallow_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROM_PUSHGATEWAY", "http://pushgw:9092")

    def _fake_post(*_args, **_kwargs):
        raise prom.requests.exceptions.RequestException("network down")

    monkeypatch.setattr(prom.requests, "post", _fake_post)

    prom.Counter("hal_events_total").inc()
    prom.flush_metrics()


def test_start_metrics_heartbeat_noop_without_pushgateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple] = []

    class _ThreadStub:
        def __init__(self, *args, **kwargs):
            created.append((args, kwargs))

        def start(self):
            raise AssertionError("Thread should not start without PROM_PUSHGATEWAY")

    monkeypatch.delenv("PROM_PUSHGATEWAY", raising=False)
    monkeypatch.setattr(prom.threading, "Thread", _ThreadStub)

    prom.start_metrics_heartbeat(interval_seconds=1)

    assert created == []


def test_start_metrics_heartbeat_starts_daemon_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = {"value": False}
    captured = {}

    class _ThreadStub:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def start(self):
            started["value"] = True

    monkeypatch.setenv("PROM_PUSHGATEWAY", "http://pushgw:9092")
    monkeypatch.setattr(prom.threading, "Thread", _ThreadStub)

    prom.start_metrics_heartbeat(interval_seconds=1)

    assert captured["daemon"] is True
    assert captured["name"] == "metrics-heartbeat"
    assert callable(captured["target"])
    assert started["value"] is True
