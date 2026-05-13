"""
OpenTelemetry tracing helpers.

Set ENABLE_TRACING=true and OTLP_ENDPOINT=http://host:4317 to export spans
to any OpenTelemetry-compatible backend (Jaeger, Datadog, Honeycomb, etc.).

The module degrades gracefully when the opentelemetry packages are not
installed — all calls become no-ops so the service keeps running.

Usage
─────
    from src.tracer import span

    with span("qdrant.search", {"top_k": 5, "collection": "docs"}):
        results = qdrant_client.search(...)
"""

import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

_tracer = None
_initialized: bool = False


def setup_tracing(service_name: str, otlp_endpoint: str, enabled: bool) -> None:
    """
    Initialise OpenTelemetry.  Call once at application startup.

    If enabled=False or packages are missing this is a safe no-op.
    """
    global _tracer, _initialized

    if not enabled:
        logger.info("Tracing disabled (ENABLE_TRACING=false)")
        _initialized = True
        return

    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"OTel OTLP exporter → {otlp_endpoint}")
        except ImportError:
            logger.warning(
                "OTLP exporter not installed — spans stay in-process only. "
                "pip install opentelemetry-exporter-otlp-proto-grpc"
            )

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        _initialized = True
        logger.info(f"OpenTelemetry tracing enabled for service '{service_name}'")

    except ImportError:
        logger.warning(
            "opentelemetry packages not installed — tracing disabled. "
            "pip install opentelemetry-api opentelemetry-sdk"
        )
        _initialized = True


@contextmanager
def span(name: str, attributes: Optional[dict] = None):
    """
    Context manager that wraps a code block in an OTel span.
    Is a harmless no-op when tracing is disabled or not installed.
    """
    if _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        yield s
