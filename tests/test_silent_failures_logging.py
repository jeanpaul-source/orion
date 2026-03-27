import builtins
import logging

import requests


def test_prometheus_query_logs_warning_on_request_exception(monkeypatch, caplog):
    caplog.set_level("WARNING")

    def _raise(*_args, **_kwargs):
        raise requests.exceptions.RequestException("boom")

    # Patch the requests.get used by hal.prometheus
    monkeypatch.setattr("hal.prometheus.requests.get", _raise)

    from hal.prometheus import PrometheusClient

    prom = PrometheusClient("http://localhost:9090")
    res = prom.query("up")
    assert res == []
    assert any("Prometheus query failed" in r.getMessage() for r in caplog.records)


def test_prometheus_scalar_parse_logs(caplog, monkeypatch):
    from hal.prometheus import PrometheusClient

    caplog.set_level(logging.WARNING)

    def fake_query(self, promql):
        return [{"value": ["0", "not-a-number"]}]

    monkeypatch.setattr("hal.prometheus.PrometheusClient.query", fake_query)

    pc = PrometheusClient("http://localhost:9090")
    val = pc.scalar("x")
    assert val is None
    assert "Prometheus scalar parse failed" in caplog.text


def test_prometheus_range_query_logs(caplog, monkeypatch):
    from hal.prometheus import PrometheusClient

    caplog.set_level(logging.WARNING)

    def fake_get(*args, **kwargs):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr("hal.prometheus.requests.get", fake_get)

    pc = PrometheusClient("http://localhost:9090")
    pts = pc.range_query("up", 0, 1, 1)
    assert pts == []
    assert "Prometheus range query failed" in caplog.text


def test_judge_load_trust_overrides_logs(caplog, monkeypatch, tmp_path):
    from hal.judge import _load_trust_overrides

    caplog.set_level(logging.WARNING)

    # Create a file that exists, but make open() raise OSError to simulate read failure
    audit_file = tmp_path / "audit.log"
    audit_file.write_text("x")

    def fake_open(*args, **kwargs):
        raise OSError("no read")

    monkeypatch.setattr(builtins, "open", fake_open)

    overrides, _demotions = _load_trust_overrides(audit_file)
    assert overrides == {}
    assert "Failed to load trust overrides" in caplog.text


def test_watchdog_component_health_logs(caplog, monkeypatch):
    import hal.healthcheck as healthcheck
    from hal import watchdog

    caplog.set_level(logging.WARNING, logger="hal.watchdog")

    def fake_run_all_checks(config):
        raise RuntimeError("boom")

    monkeypatch.setattr(healthcheck, "run_all_checks", fake_run_all_checks)

    res = watchdog._check_component_health(config=object())
    assert res is None
    assert "Component health check failed" in caplog.text
