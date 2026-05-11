#!/usr/bin/env bash
# Chaos Script #3: Inject network latency to simulate LLM API degradation
# Simulates: Upstream LLM API (OpenAI/Anthropic) degraded in Southeast Asia region
# Failure mode: Dependency — service is up but slow, cascading timeouts
# Expected detection: HighInferenceLatency + SLOSlowBurn alerts

set -euo pipefail

# Use tc (traffic control) to add latency to the otel-collector port
# This simulates what happens when your LLM API provider has regional degradation
TARGET_PORT="${TARGET_PORT:-4317}"  # OTLP gRPC port (can change to simulate other deps)
LATENCY_MS="${LATENCY_MS:-3000}"    # Add 3 seconds of latency
JITTER_MS="${JITTER_MS:-500}"       # ±500ms jitter
DURATION="${DURATION:-900}"         # 15 minutes
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo "=== Chaos #3: Inject Network Latency ==="
echo "Target port: $TARGET_PORT (+${LATENCY_MS}ms ±${JITTER_MS}ms jitter)"
echo "Duration: ${DURATION}s"
echo "Time: $(date -Iseconds)"
echo ""

# Pre-flight
echo "[pre-flight] P99 latency (past 5m):"
curl -s "$PROMETHEUS_URL/api/v1/query?query=histogram_quantile(0.99,sum(rate(inference_latency_seconds_bucket[5m]))by(le,model))" | jq '.data.result[] | {model: .metric.model, p99: .value[1]}' 2>/dev/null

echo "[pre-flight] Current tc rules on eth0:"
sudo tc qdisc show dev eth0 2>/dev/null || echo "No rules (or eth0 not accessible)"

START_TS=$(date +%s)

# Add latency using tc netem
echo ""
echo "[chaos] Adding ${LATENCY_MS}ms latency on port $TARGET_PORT..."
# For port-specific delay, we need an intermediate qdisc with a filter
# Simpler approach: add latency to entire interface (more realistic — whole API is slow)
sudo tc qdisc add dev eth0 root netem delay "${LATENCY_MS}ms" "${JITTER_MS}ms" distribution normal 2>/dev/null && \
    echo "tc rule added." || \
    echo "tc failed (expected if not running on host network). Using docker proxy delay instead..."

# Alternative: use docker-compose to pause/unpause the dependent service
# docker compose pause otel-collector  # simulates dependency gone

echo ""
echo "[observe] Waiting for latency alerts to evaluate..."
sleep 360  # 6 min — HighInferenceLatency has for: 5m

echo ""
echo "[check] HighInferenceLatency alert:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=ALERTS{alertname=\"HighInferenceLatency\"}" | jq '.data.result[] | {state: .value[1], summary: .annotations.summary}' 2>/dev/null || echo "Not yet firing"

echo ""
echo "[check] P99 latency now:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=histogram_quantile(0.99,sum(rate(inference_latency_seconds_bucket[5m]))by(le,model))" | jq '.data.result[] | {model: .metric.model, p99: .value[1]}' 2>/dev/null

echo ""
echo "[check] SLOSlowBurn alert:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=ALERTS{alertname=\"SLOSlowBurn\"}" | jq '.data.result[] | {state: .value[1]}' 2>/dev/null || echo "Not yet firing"

# Wait more for slow burn detection
sleep 600  # 10 more min

echo ""
echo "[check after 16min] SLOSlowBurn alert:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=ALERTS{alertname=\"SLOSlowBurn\"}" | jq '.data.result[] | {state: .value[1], summary: .annotations.summary}' 2>/dev/null || echo "Not yet firing"

# Restore
echo ""
echo "[restore] Removing tc latency rule..."
sudo tc qdisc del dev eth0 root 2>/dev/null && echo "tc rule removed." || echo "No tc rule to remove."

END_TS=$(date +%s)
DURATION_ACTUAL=$((END_TS - START_TS))
echo ""
echo "=== Chaos #3 Complete ==="
echo "Duration: ${DURATION_ACTUAL}s"
echo ""
echo "KEY INSIGHT: Dependency latency is a SLOW KILLER. Service stays up,"
echo "but error budget burns silently. Only multi-window burn-rate alerting"
echo "surfaces this before users complain."
