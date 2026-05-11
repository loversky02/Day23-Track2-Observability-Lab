"""Prometheus + OTel + structlog wiring.

Single source of truth for the metric/span/log namespace.
"""
from __future__ import annotations

import logging
import os
import sys

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

# ── Prometheus metrics ────────────────────────────────────────
INFERENCE_REQUESTS = Counter(
    "inference_requests_total",
    "Total inference requests",
    ["model", "status"],
)
INFERENCE_LATENCY = Histogram(
    "inference_latency_seconds",
    "Inference end-to-end latency",
    ["model"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)
INFERENCE_ACTIVE = Gauge(
    "inference_active_gauge",
    "In-flight inference requests",
)
INFERENCE_TOKENS = Counter(
    "inference_tokens_total",
    "Tokens processed (input/output)",
    ["model", "direction"],
)
INFERENCE_QUALITY = Gauge(
    "inference_quality_score",
    "Latest eval-as-metric quality score [0,1]",
    ["model"],
)
GPU_UTIL = Gauge(
    "gpu_utilization_percent",
    "Simulated GPU utilization [0,100]",
)

tracer = trace.get_tracer(__name__)


def setup_otel() -> None:
    """Configure OTLP trace export + FastAPI auto-instrumentation + Pyroscope profiling."""
    global tracer  # refresh after provider is set

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "inference-api"),
            "service.namespace": "aicb",
            "deployment.environment": os.getenv(
                "DEPLOY_ENV",
                "lab",
            ),
        }
    )
    provider = TracerProvider(resource=resource)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)  # re-obtain after provider is set

    # Auto-instrument FastAPI handlers (creates server spans for every route)
    from fastapi import FastAPI  # local import: only needed at setup

    FastAPIInstrumentor().instrument()
    _configure_logging()

    # BONUS B1: Pyroscope continuous profiling
    try:
        import pyroscope

        pyroscope.configure(
            app_name=os.getenv("PYROSCOPE_APP_NAME", "inference-api"),
            server_address=os.getenv("PYROSCOPE_SERVER", "http://pyroscope:4040"),
            sample_rate=100,
            oncpu=True,
            report_pid=True,
            report_thread_id=True,
            report_thread_name=True,
        )
    except Exception:
        pass  # pyroscope not required for core lab


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=os.getenv("LOG_LEVEL", "INFO"),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_log(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
