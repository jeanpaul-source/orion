"""OpenTelemetry tracing setup for HAL.

Call setup_tracing() once at startup (in main.py). All instrumented code
imports get_tracer() to obtain the configured tracer.

If the OTLP endpoint is unreachable or opentelemetry packages are absent,
all spans are silently no-ops — HAL continues working normally.

Default endpoint: http://localhost:4318 (AI Toolkit trace viewer / OTLP HTTP).
Override with the OTLP_ENDPOINT env var.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_tracer = None


def setup_tracing(endpoint: str | None = None) -> None:
    """Configure the global OTel tracer provider with an OTLP HTTP exporter."""
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        url = (endpoint or os.getenv("OTLP_ENDPOINT", "http://localhost:4318")).rstrip("/")
        resource = Resource(attributes={SERVICE_NAME: "hal"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{url}/v1/traces"))
        )
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("hal", "1.0.0")
        logger.debug("Tracing enabled → %s", url)
    except ImportError:
        logger.debug("opentelemetry not installed — tracing disabled")
    except Exception as exc:
        logger.debug("Tracing setup failed (%s) — continuing without tracing", exc)


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
