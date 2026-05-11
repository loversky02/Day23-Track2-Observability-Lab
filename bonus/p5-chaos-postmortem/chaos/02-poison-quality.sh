#!/usr/bin/env bash
# Chaos Script #2: Poison inference quality by injecting fail=true requests
# Simulates: Model degradation where 20% of requests return garbage / error
# Failure mode: Data/Model — quality drops but service stays "up"
# Expected detection: InferenceQualityDrop alert fires within ~10 min
#
# This is the SILENT FAILURE — service returns 200 OK but responses are wrong.
# Default Prometheus alerts (ServiceDown, HighLatency) will NOT catch this.

set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8000}"
DURATION="${DURATION:-600}"  # 10 minutes of poisoning
POISON_RATIO="${POISON_RATIO:-0.20}"  # 20% of requests fail
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo "=== Chaos #2: Poison Quality ==="
echo "Target: $APP_URL/predict"
echo "Poison ratio: $POISON_RATIO (${DURATION}s duration)"
echo "Time: $(date -Iseconds)"
echo ""

# Pre-flight
echo "[pre-flight] Current quality score:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=inference_quality_score" | jq '.data.result[] | {model: .metric.model, score: .value[1]}' 2>/dev/null

echo "[pre-flight] Current error rate (past 5m):"
curl -s "$PROMETHEUS_URL/api/v1/query?query=sum(rate(inference_requests_total{status=\"error\"}[5m]))/sum(rate(inference_requests_total[5m]))" | jq '.data.result[0].value[1]' 2>/dev/null

START_TS=$(date +%s)

echo ""
echo "[chaos] Injecting poisoned requests for ${DURATION}s..."
END_TIME=$((START_TS + DURATION))

POISON_COUNT=0
TOTAL_COUNT=0
while [ "$(date +%s)" -lt "$END_TIME" ]; do
    if awk "BEGIN {exit !(rand() < $POISON_RATIO)}"; then
        # Poisoned request — simulates model returning garbage
        curl -s -X POST "$APP_URL/predict" \
            -H "Content-Type: application/json" \
            -d "{\"prompt\": \"$(shuf -n 3 /usr/share/dict/words 2>/dev/null | tr '\n' ' ' || echo 'garbage input')\", \"model\": \"llama3-mock\", \"fail\": true}" \
            > /dev/null 2>&1 &
        POISON_COUNT=$((POISON_COUNT + 1))
    else
        # Normal request — keeps service looking healthy
        curl -s -X POST "$APP_URL/predict" \
            -H "Content-Type: application/json" \
            -d "{\"prompt\": \"What is the capital of France?\", \"model\": \"llama3-mock\"}" \
            > /dev/null 2>&1 &
    fi
    TOTAL_COUNT=$((TOTAL_COUNT + 1))

    # 10 requests/second
    sleep 0.1

    # Report every 50 requests
    if [ $((TOTAL_COUNT % 50)) -eq 0 ]; then
        echo "  [$TOTAL_COUNT req] poison=$POISON_COUNT ($(awk "BEGIN {printf \"%.0f\", $POISON_COUNT/$TOTAL_COUNT*100}")%)"
    fi
done

wait

echo ""
echo "[observe] Waiting 5m for quality alert evaluation..."
sleep 300

echo ""
echo "[check] InferenceQualityDrop alert:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=ALERTS{alertname=\"InferenceQualityDrop\"}" | jq '.data.result[] | {state: .value[1], summary: .annotations.summary}' 2>/dev/null || echo "Alert not yet firing (may need more time)"

echo ""
echo "[check] Quality score trend:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=avg(inference_quality_score)by(model)" | jq '.data.result[] | {model: .metric.model, score: .value[1]}' 2>/dev/null

echo ""
echo "[check] Error rate (past 5m):"
curl -s "$PROMETHEUS_URL/api/v1/query?query=sum(rate(inference_requests_total{status=\"error\"}[5m]))/sum(rate(inference_requests_total[5m]))" | jq '.data.result[0].value[1]' 2>/dev/null

END_TS=$(date +%s)
DURATION_ACTUAL=$((END_TS - START_TS))
echo ""
echo "=== Chaos #2 Complete ==="
echo "Total requests: $TOTAL_COUNT  Poisoned: $POISON_COUNT ($(awk "BEGIN {printf \"%.1f\", $POISON_COUNT/$TOTAL_COUNT*100}")%)"
echo "Duration: ${DURATION_ACTUAL}s"
echo ""
echo "KEY INSIGHT: Service was UP the entire time. Only the quality metric caught this."
echo "If you only alert on 'up' and 'latency', this failure is INVISIBLE."
