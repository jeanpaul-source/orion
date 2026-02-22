# AI Toolkit Tracing Integration for ORION
# Shared OpenTelemetry utilities for all ORION components

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def setup_tracing(
    service_name: str,
    service_version: str = "1.0.0",
    otlp_endpoint: str = "http://localhost:4318/v1/traces",
    enable: bool = True,
) -> Optional[trace.Tracer]:
    """
    Set up OpenTelemetry tracing for ORION components.

    Uses AI Toolkit's trace collector (localhost:4318).

    Args:
        service_name: Name of the service (e.g., "orion-core", "devia")
        service_version: Version of the service
        otlp_endpoint: OTLP HTTP endpoint (default: AI Toolkit collector)
        enable: Whether to enable tracing

    Returns:
        Tracer instance or None if disabled

    Usage:
        tracer = setup_tracing("orion-core", "1.1.0")
        with tracer.start_as_current_span("my-operation"):
            # Your code here
            pass
    """
    if not enable:
        logger.info("Tracing disabled")
        return None

    try:
        # Create resource with service metadata
        resource = Resource(
            attributes={
                SERVICE_NAME: service_name,
                SERVICE_VERSION: service_version,
                "orion.component": service_name,
            }
        )

        # Set up tracer provider
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        # Configure OTLP exporter (AI Toolkit collector)
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(span_processor)

        # Auto-instrument common libraries
        RequestsInstrumentor().instrument()
        AioHttpClientInstrumentor().instrument()

        logger.info(f"✅ Tracing enabled for {service_name} → {otlp_endpoint}")

        # Return tracer for manual instrumentation
        return trace.get_tracer(service_name, service_version)

    except Exception as e:
        logger.error(f"❌ Failed to set up tracing: {e}")
        return None


def instrument_fastapi(app, service_name: str = "fastapi-app"):
    """
    Auto-instrument a FastAPI application.

    Args:
        app: FastAPI application instance
        service_name: Service name for traces

    Usage:
        from fastapi import FastAPI
        app = FastAPI()
        instrument_fastapi(app, "orion-core")
    """
    try:
        FastAPIInstrumentor.instrument_app(app)
        logger.info(f"✅ FastAPI instrumented for {service_name}")
    except Exception as e:
        logger.error(f"❌ Failed to instrument FastAPI: {e}")


def add_span_attributes(span, **attributes):
    """
    Add custom attributes to the current span.

    Args:
        span: Current span
        **attributes: Key-value pairs to add

    Usage:
        with tracer.start_as_current_span("query") as span:
            add_span_attributes(span,
                subsystem="knowledge",
                query="Kubernetes best practices",
                top_k=5
            )
    """
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, str(value))


def trace_llm_call(tracer, model: str, prompt: str, response: str, latency_ms: float):
    """
    Create a span for LLM calls with standard attributes.

    Args:
        tracer: Tracer instance
        model: Model name (e.g., "Qwen2.5-14B")
        prompt: User prompt
        response: LLM response
        latency_ms: Call latency in milliseconds

    Usage:
        trace_llm_call(tracer, "Qwen2.5-14B", prompt, response, 1234.5)
    """
    with tracer.start_as_current_span("llm.call") as span:
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.prompt_length", len(prompt))
        span.set_attribute("llm.response_length", len(response))
        span.set_attribute("llm.latency_ms", latency_ms)


def trace_rag_retrieval(
    tracer, query: str, top_k: int, results_count: int, latency_ms: float
):
    """
    Create a span for RAG retrieval operations.

    Args:
        tracer: Tracer instance
        query: Search query
        top_k: Number of results requested
        results_count: Number of results returned
        latency_ms: Retrieval latency in milliseconds
    """
    with tracer.start_as_current_span("rag.retrieval") as span:
        span.set_attribute("rag.query", query)
        span.set_attribute("rag.top_k", top_k)
        span.set_attribute("rag.results_count", results_count)
        span.set_attribute("rag.latency_ms", latency_ms)


def trace_tool_call(tracer, tool_name: str, args: dict, result: str, success: bool):
    """
    Create a span for agent tool calls.

    Args:
        tracer: Tracer instance
        tool_name: Name of the tool
        args: Tool arguments
        result: Tool result
        success: Whether the tool call succeeded
    """
    with tracer.start_as_current_span(f"tool.{tool_name}") as span:
        span.set_attribute("tool.name", tool_name)
        span.set_attribute("tool.args", str(args))
        span.set_attribute("tool.result_length", len(result))
        span.set_attribute("tool.success", success)


# Convenience function for ORION components
def get_orion_tracer(
    component: str, enable_env_var: str = "ORION_ENABLE_TRACING"
) -> Optional[trace.Tracer]:
    """
    Get a tracer for an ORION component with automatic configuration.

    Args:
        component: Component name (e.g., "core", "devia", "harvester")
        enable_env_var: Environment variable to check for enabling tracing

    Returns:
        Tracer instance or None

    Usage:
        tracer = get_orion_tracer("core")
        if tracer:
            with tracer.start_as_current_span("my-operation"):
                # Your code
                pass
    """
    import os

    enable = os.getenv(enable_env_var, "true").lower() == "true"

    service_name = f"orion-{component}"
    return setup_tracing(service_name, enable=enable)
