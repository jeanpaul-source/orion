"""OpenTelemetry tracing setup for HAL.

Call setup_tracing() once at startup (in main.py). All instrumented code
imports get_tracer() to obtain the configured tracer.

If the OTLP endpoint is unreachable or opentelemetry packages are absent,
the provider is not wired and all spans are no-ops — HAL continues normally.

Default endpoint: http://localhost:4318 (AI Toolkit trace viewer / OTLP HTTP).
Override with the OTLP_ENDPOINT env var.

Disable entirely:  OTEL_SDK_DISABLED=true   (default in eval/run_eval.py)
Verbose endpoint:  OTLP_ENDPOINT=http://host:4318
"""

from __future__ import annotations

import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_tracer = None


def setup_tracing(endpoint: str | None = None) -> None:
    """Configure the global OTel tracer provider with an OTLP HTTP exporter.

    Behaviour summary (visible at INFO log level):
      OTEL_SDK_DISABLED=true  -> returns immediately, no SDK wiring.
      opentelemetry missing   -> returns immediately.
      endpoint unreachable    -> DEBUG log, returns without wiring any provider.
      everything OK           -> INFO confirming endpoint URL.
    """
    global _tracer

    # Fast-exit: operator explicitly disabled tracing -- no SDK wiring at all.
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        logger.info(
            "Tracing disabled (OTEL_SDK_DISABLED=true). "
            "Unset or set to 'false' to enable."
        )
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        url = (
            endpoint or os.getenv("OTLP_ENDPOINT") or "http://localhost:4318"
        ).rstrip("/")

        # Probe before wiring the provider. If the endpoint is down, skip setup
        # entirely — no BatchSpanProcessor thread, no silently-dropped spans.
        if not _probe_endpoint(url):
            return

        resource = Resource(attributes={SERVICE_NAME: "hal"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{url}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("hal", "1.0.0")

        logger.info("Tracing enabled -> %s", url)
    except ImportError:
        logger.info("opentelemetry not installed -- tracing disabled")
    except Exception as exc:
        logger.info("Tracing setup failed (%s) -- continuing without tracing", exc)


def _probe_endpoint(url: str) -> bool:
    """TCP-probe the OTLP endpoint. Returns True if reachable, False otherwise.

    Called before the provider is constructed so that an unreachable endpoint
    causes a clean early-exit rather than a running BatchSpanProcessor that
    silently drops every span it tries to export.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 4318)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        logger.debug(
            "OTLP endpoint unreachable at %s (TCP %s:%d) -- tracing disabled. "
            "Set OTEL_SDK_DISABLED=true to skip this probe.",
            url,
            host,
            port,
        )
        return False


def get_tracer():
    """Return the configured tracer, or a no-op tracer if setup_tracing() was not called."""
    if _tracer is not None:
        return _tracer
    try:
        from opentelemetry import trace

        return trace.get_tracer("hal")
    except ImportError:
        return _NoOpTracer()


# --------------------------------------------------------------------------- #
# Minimal no-op fallback — used only when opentelemetry-api is not installed. #
# --------------------------------------------------------------------------- #


class _NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def set_attribute(self, *_):
        pass

    def record_exception(self, *_):
        pass


class _NoOpTracer:
    def start_as_current_span(self, *_args, **_kwargs):
        return _NoOpSpan()
