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


# ---------------------------------------------------------------------------
# range_query tests
# ---------------------------------------------------------------------------


def test_range_query_returns_tuples(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful /query_range response is parsed into (timestamp, value) tuples."""
    fake_response = SimpleNamespace(
        json=lambda: {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {},
                        "values": [
                            [1700000000, "12.5"],
                            [1700000060, "13.0"],
                            [1700000120, "14.2"],
                        ],
                    }
                ]
            },
        }
    )
    monkeypatch.setattr(
        prom.requests,
        "get",
        lambda *a, **kw: fake_response,
    )
    client = prom.PrometheusClient("http://prom:9091")
    result = client.range_query("node_load1", start=1700000000, end=1700000120, step=60)
    assert result == [
        (1700000000.0, 12.5),
        (1700000060.0, 13.0),
        (1700000120.0, 14.2),
    ]


def test_range_query_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty result list from Prometheus returns []."""
    fake_response = SimpleNamespace(
        json=lambda: {
            "status": "success",
            "data": {"result": []},
        }
    )
    monkeypatch.setattr(prom.requests, "get", lambda *a, **kw: fake_response)
    client = prom.PrometheusClient("http://prom:9091")
    assert client.range_query("node_load1", start=0, end=3600, step=60) == []


def test_range_query_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """RequestException is swallowed; returns []."""

    def _fail(*a, **kw):
        raise prom.requests.exceptions.RequestException("timeout")

    monkeypatch.setattr(prom.requests, "get", _fail)
    client = prom.PrometheusClient("http://prom:9091")
    assert client.range_query("node_load1", start=0, end=3600, step=60) == []


# ---------------------------------------------------------------------------
# trend tests
# ---------------------------------------------------------------------------


def test_trend_rising(monkeypatch: pytest.MonkeyPatch) -> None:
    """60 strictly increasing points → direction 'rising', correct delta."""
    # Build 60 points linearly from 10.0 to 20.0 over 3600 s
    points = [(float(i * 60), 10.0 + i * (10.0 / 59)) for i in range(60)]
    client = prom.PrometheusClient("http://prom:9091")
    monkeypatch.setattr(client, "range_query", lambda *a, **kw: points)
    result = client.trend("node_load1", window="1h")
    assert result is not None
    assert result["direction"] == "rising"
    assert result["first"] == round(points[0][1], 2)
    assert result["last"] == round(points[-1][1], 2)
    assert result["delta"] == round(points[-1][1] - points[0][1], 2)
    assert result["delta_per_hour"] == round(result["delta"] / 1, 2)


def test_trend_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flat points within threshold → direction 'stable'."""
    # All values identical — delta = 0
    points = [(float(i * 60), 55.0) for i in range(60)]
    client = prom.PrometheusClient("http://prom:9091")
    monkeypatch.setattr(client, "range_query", lambda *a, **kw: points)
    result = client.trend("node_load1", window="1h")
    assert result is not None
    assert result["direction"] == "stable"
    assert result["delta"] == 0.0


def test_trend_insufficient_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fewer than 2 data points → trend() returns None."""
    client = prom.PrometheusClient("http://prom:9091")
    monkeypatch.setattr(client, "range_query", lambda *a, **kw: [(1700000000.0, 42.0)])
    assert client.trend("node_load1", window="1h") is None


def test_trend_falling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strictly decreasing points → direction 'falling'."""
    points = [(float(i * 60), 80.0 - i * (20.0 / 59)) for i in range(60)]
    client = prom.PrometheusClient("http://prom:9091")
    monkeypatch.setattr(client, "range_query", lambda *a, **kw: points)
    result = client.trend("node_load1", window="1h")
    assert result is not None
    assert result["direction"] == "falling"
    assert result["delta"] < 0
