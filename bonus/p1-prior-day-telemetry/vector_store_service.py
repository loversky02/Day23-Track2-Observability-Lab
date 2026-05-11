"""Day 19 Vector Store — retrofitted with OpenTelemetry instrumentation.

Simulates a vector store service (Qdrant-style) with:
  - Search endpoint (ANN retrieval)
  - Upsert endpoint (embedding ingestion)
  - Index stats endpoint

Emits: Prometheus metrics + OTLP traces + structured JSON logs.
Designed as a standalone service that can be docker-compose'd alongside the core stack.
"""
from __future__ import annotations

import os
import time
import uuid
import math
import random
import logging
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, Counter, Gauge, Histogram
from pydantic import BaseModel

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# ── Prometheus metrics ──────────────────────────────────────────
VECTOR_SEARCH_REQUESTS = Counter(
    "vector_search_requests_total",
    "Total vector search requests",
    ["collection", "status"],
)
VECTOR_SEARCH_LATENCY = Histogram(
    "vector_search_latency_seconds",
    "End-to-end vector search latency",
    ["collection"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
VECTOR_INDEX_SIZE = Gauge(
    "vector_index_size_bytes",
    "Approximate vector index size in bytes",
    ["collection"],
)
VECTOR_COUNT = Gauge(
    "vector_count_total",
    "Total vectors in collection",
    ["collection"],
)
RETRIEVAL_RECALL = Gauge(
    "vector_retrieval_recall_at10",
    "Simulated recall@10 score [0,1] — quality metric",
    ["collection"],
)
GPU_MEMORY = Gauge(
    "vector_gpu_memory_bytes",
    "GPU memory used by vector index (simulated)",
    ["device"],
)

# ── OTel setup ───────────────────────────────────────────────────
def setup_otel() -> None:
    resource = Resource.create({
        "service.name": "vector-store",
        "service.namespace": "aicb",
        "deployment.environment": os.getenv("DEPLOY_ENV", "lab"),
    })

    # Traces
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
            insecure=True,
        ))
    )
    trace.set_tracer_provider(tp)

    # Metrics
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
            insecure=True,
        ),
        export_interval_millis=15_000,
    )
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)

    FastAPIInstrumentor().instrument()
    _setup_logging()


def _setup_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
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


log = structlog.get_logger("vector-store")
tracer = trace.get_tracer(__name__)

# ── Simulated vector store state ─────────────────────────────────
COLLECTIONS: dict[str, int] = {
    "product-embeddings": 500_000,
    "user-queries": 120_000,
    "doc-chunks": 1_200_000,
}


def _simulate_search_latency(collection: str) -> float:
    """Simulate realistic ANN search: most fast, occasional slow."""
    base = random.gauss(0.015, 0.008)  # ~15ms mean
    # 1% of queries are slow (disk fetch, queueing)
    if random.random() < 0.01:
        base += random.expovariate(1 / 0.5)  # add 0-2s tail
    return max(0.001, base)


def _simulate_recall(collection: str) -> float:
    """Simulate recall@10 degrading as index grows or with noise."""
    n = COLLECTIONS.get(collection, 100_000)
    # Larger index = slightly harder to get perfect recall
    base_recall = 0.98 - (math.log10(n) - 4) * 0.03
    noise = random.gauss(0, 0.02)
    return round(max(0.0, min(1.0, base_recall + noise)), 4)


def _simulate_gpu_memory() -> float:
    """Simulate GPU FR with index growth."""
    total_vectors = sum(COLLECTIONS.values())
    # 768-dim float32 = 3072 bytes per vector, plus index overhead ~30%
    return total_vectors * 3072 * 1.3


# ── FastAPI app ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_otel()
    yield


app = FastAPI(title="day19-vector-store", lifespan=lifespan)


class SearchRequest(BaseModel):
    collection: str = "product-embeddings"
    vector: list[float] = [0.0] * 768
    top_k: int = 10


class SearchHit(BaseModel):
    id: str
    score: float


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    latency_ms: float
    trace_id: str
    recall_at10: float


class UpsertRequest(BaseModel):
    collection: str
    vectors: list[list[float]]
    ids: list[str] | None = None


class UpsertResponse(BaseModel):
    inserted: int
    collection_size: int
    trace_id: str


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint() -> Response:
    VECTOR_INDEX_SIZE.labels(collection="product-embeddings").set(
        COLLECTIONS["product-embeddings"] * 3072 * 1.3
    )
    VECTOR_INDEX_SIZE.labels(collection="user-queries").set(
        COLLECTIONS["user-queries"] * 3072 * 1.3
    )
    VECTOR_INDEX_SIZE.labels(collection="doc-chunks").set(
        COLLECTIONS["doc-chunks"] * 3072 * 1.3
    )
    VECTOR_COUNT.labels(collection="product-embeddings").set(COLLECTIONS["product-embeddings"])
    VECTOR_COUNT.labels(collection="user-queries").set(COLLECTIONS["user-queries"])
    VECTOR_COUNT.labels(collection="doc-chunks").set(COLLECTIONS["doc-chunks"])
    GPU_MEMORY.labels(device="cuda:0").set(_simulate_gpu_memory())
    RETRIEVAL_RECALL.labels(collection="product-embeddings").set(_simulate_recall("product-embeddings"))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    start = time.perf_counter()
    with tracer.start_as_current_span("vector-search") as span:
        span.set_attribute("collection", req.collection)
        span.set_attribute("top_k", req.top_k)
        span.set_attribute("vector.dim", len(req.vector))

        collection = req.collection
        if collection not in COLLECTIONS:
            VECTOR_SEARCH_REQUESTS.labels(collection=collection, status="error").inc()
            raise HTTPException(status_code=404, detail=f"collection '{collection}' not found")

        # Simulate sub-spans for each search phase
        with tracer.start_as_current_span("quantize-query"):
            time.sleep(random.gauss(0.002, 0.0005))

        with tracer.start_as_current_span("coarse-search") as cs:
            cs.set_attribute("nlist", 1024)
            cs.set_attribute("nprobe", 32)
            time.sleep(_simulate_search_latency(collection) * 0.6)

        with tracer.start_as_current_span("fine-rerank") as fr:
            fr.set_attribute("candidates", min(req.top_k * 10, 100))
            time.sleep(_simulate_search_latency(collection) * 0.3)

        recall = _simulate_recall(collection)
        hits = [
            SearchHit(id=uuid.uuid4().hex[:12], score=round(random.uniform(0.7, 0.99), 4))
            for _ in range(req.top_k)
        ]
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        VECTOR_SEARCH_REQUESTS.labels(collection=collection, status="ok").inc()
        VECTOR_SEARCH_LATENCY.labels(collection=collection).observe(elapsed_ms / 1000)
        RETRIEVAL_RECALL.labels(collection=collection).set(recall)

        trace_id = format(span.get_span_context().trace_id, "032x")
        log.info(
            "vector search completed",
            collection=collection,
            top_k=req.top_k,
            hits=len(hits),
            latency_ms=elapsed_ms,
            recall=recall,
            trace_id=trace_id,
        )
        return SearchResponse(hits=hits, latency_ms=elapsed_ms, trace_id=trace_id, recall_at10=recall)


@app.post("/upsert", response_model=UpsertResponse)
def upsert(req: UpsertRequest) -> UpsertResponse:
    with tracer.start_as_current_span("vector-upsert") as span:
        span.set_attribute("collection", req.collection)
        span.set_attribute("vectors.count", len(req.vectors))

        if req.collection not in COLLECTIONS:
            COLLECTIONS[req.collection] = 0

        inserted = len(req.vectors)
        COLLECTIONS[req.collection] += inserted

        trace_id = format(span.get_span_context().trace_id, "032x")
        log.info("vectors upserted", collection=req.collection, inserted=inserted, trace_id=trace_id)
        return UpsertResponse(inserted=inserted, collection_size=COLLECTIONS[req.collection], trace_id=trace_id)


@app.get("/stats")
def stats() -> dict:
    return {
        "collections": COLLECTIONS,
        "total_vectors": sum(COLLECTIONS.values()),
        "gpu_memory_estimated_bytes": _simulate_gpu_memory(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
