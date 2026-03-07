"""Tests for hal/tracing.py — OTel setup, endpoint probing, and no-op fallback.

All tests are offline. No real OTLP endpoint or opentelemetry SDK is needed;
the setup paths are exercised via monkeypatching.
"""

from __future__ import annotations

import socket

import pytest

from hal import tracing

# =========================================================================
# _probe_endpoint()
# =========================================================================


class TestProbeEndpoint:
    def test_returns_true_when_port_is_reachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TCP connect succeeds → returns True."""

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        monkeypatch.setattr(
            socket, "create_connection", lambda addr, timeout: FakeSocket()
        )
        assert tracing._probe_endpoint("http://localhost:4318") is True

    def test_returns_false_when_port_is_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TCP connect raises OSError → returns False."""

        def raise_os_error(*_args, **_kwargs):
            raise OSError("Connection refused")

        monkeypatch.setattr(socket, "create_connection", raise_os_error)
        assert tracing._probe_endpoint("http://localhost:4318") is False

    def test_parses_custom_port_from_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom port in the URL is used for the TCP probe."""
        probed_addr: list[tuple] = []

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        def capture_connect(addr, timeout):
            probed_addr.append(addr)
            return FakeSocket()

        monkeypatch.setattr(socket, "create_connection", capture_connect)
        tracing._probe_endpoint("http://tempo-host:9999")
        assert probed_addr[0] == ("tempo-host", 9999)

    def test_defaults_to_443_for_https(self, monkeypatch: pytest.MonkeyPatch) -> None:
        probed_addr: list[tuple] = []

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

        def capture_connect(addr, timeout):
            probed_addr.append(addr)
            return FakeSocket()

        monkeypatch.setattr(socket, "create_connection", capture_connect)
        tracing._probe_endpoint("https://otel.example.com")
        assert probed_addr[0][1] == 443


# =========================================================================
# setup_tracing()
# =========================================================================


class TestSetupTracing:
    def test_skips_when_otel_sdk_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OTEL_SDK_DISABLED=true → returns immediately, no probe."""
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        # Reset global state
        monkeypatch.setattr(tracing, "_tracer", None)
        tracing.setup_tracing()
        # _tracer should still be None — nothing was wired
        assert tracing._tracer is None

    def test_skips_when_otel_sdk_disabled_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_SDK_DISABLED", "True")
        monkeypatch.setattr(tracing, "_tracer", None)
        tracing.setup_tracing()
        assert tracing._tracer is None

    def test_skips_when_endpoint_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If _probe_endpoint returns False, setup_tracing does nothing."""
        monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
        monkeypatch.setattr(tracing, "_tracer", None)
        monkeypatch.setattr(tracing, "_probe_endpoint", lambda url: False)
        tracing.setup_tracing("http://unreachable:4318")
        assert tracing._tracer is None

    def test_handles_import_error_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If opentelemetry is not installed, setup returns without error."""
        monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
        monkeypatch.setattr(tracing, "_tracer", None)

        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("opentelemetry"):
                raise ImportError("No module named 'opentelemetry'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        tracing.setup_tracing("http://localhost:4318")
        assert tracing._tracer is None


# =========================================================================
# get_tracer()
# =========================================================================


class TestGetTracer:
    def test_returns_configured_tracer_when_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = object()
        monkeypatch.setattr(tracing, "_tracer", sentinel)
        assert tracing.get_tracer() is sentinel

    def test_returns_noop_tracer_when_otel_not_installed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _tracer is None and opentelemetry is absent, return _NoOpTracer."""
        monkeypatch.setattr(tracing, "_tracer", None)

        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("opentelemetry"):
                raise ImportError("No module")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        tracer = tracing.get_tracer()
        assert isinstance(tracer, tracing._NoOpTracer)


# =========================================================================
# _NoOpSpan / _NoOpTracer
# =========================================================================


class TestNoOpSpan:
    def test_context_manager_returns_self(self) -> None:
        span = tracing._NoOpSpan()
        with span as s:
            assert s is span

    def test_set_attribute_is_noop(self) -> None:
        span = tracing._NoOpSpan()
        # Should not raise
        span.set_attribute("key", "value")

    def test_record_exception_is_noop(self) -> None:
        span = tracing._NoOpSpan()
        span.record_exception(RuntimeError("boom"))


class TestNoOpTracer:
    def test_start_as_current_span_returns_noop_span(self) -> None:
        tracer = tracing._NoOpTracer()
        span = tracer.start_as_current_span("test-span")
        assert isinstance(span, tracing._NoOpSpan)

    def test_span_is_usable_as_context_manager(self) -> None:
        tracer = tracing._NoOpTracer()
        with tracer.start_as_current_span("test-span") as span:
            span.set_attribute("key", "value")
            span.record_exception(ValueError("test"))
