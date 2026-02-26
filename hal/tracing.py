"""OpenTelemetry tracing setup for HAL.

Call setup_tracing() once at startup (in main.py). All instrumented code
imports get_tracer() to obtain the configured tracer.

If the OTLP endpoint is unreachable or opentelemetry packages are absent,
all spans are silently no-ops — HAL continues working normally.

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
      endpoint unreachable    -> one WARNING, spans will be dropped.
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

        url = (endpoint or os.getenv("OTLP_ENDPOINT", "http://localhost:4318")).rstrip(
            "/"
        )
        resource = Resource(attributes={SERVICE_NAME: "hal"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{url}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("hal", "1.0.0")

        # Probe once so operators see one actionable WARNING instead of a
        # background-thread flood from BatchSpanProcessor on every export cycle.
        _probe_endpoint(url)

        logger.info("Tracing enabled -> %s", url)
    except ImportError:
        logger.info("opentelemetry not installed -- tracing disabled")
    except Exception as exc:
        logger.info("Tracing setup failed (%s) -- continuing without tracing", exc)


def _probe_endpoint(url: str) -> None:
    """TCP-probe the OTLP endpoint once at startup. Logs one WARNING if unreachable.

    Runs synchronously so the warning appears before any background
    BatchSpanProcessor export failures, giving operators a single clear
    call-to-action rather than repeated SDK-level noise.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 4318)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass  # endpoint reachable
    except OSError:
        logger.warning(
            "OTLP endpoint unreachable at %s (TCP %s:%d). "
            "Spans will be silently dropped by the background exporter. "
            "Fix the endpoint or set OTEL_SDK_DISABLED=true to silence this warning.",
            url,
            host,
            port,
        )


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

    def set_attribute(self, *_):  # noqa: ANN001
        pass

    def record_exception(self, *_):  # noqa: ANN001
        pass


class _NoOpTracer:
    def start_as_current_span(self, *_args, **_kwargs):
        return _NoOpSpan()
