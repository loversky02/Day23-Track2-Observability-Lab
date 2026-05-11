#!/usr/bin/env bash
# Chaos Script #1: Kill the inference service container
# Simulates: OOM kill, segfault, or accidental docker stop in production
# Failure mode: Infra — complete service outage
# Expected detection: ServiceDown alert fires within ~1.5 min

set -euo pipefail

APP_CONTAINER="${APP_CONTAINER:-day23-app}"
WAIT_FOR_ALERT="${WAIT_FOR_ALERT:-120}"  # seconds to wait for alert to fire
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo "=== Chaos #1: Kill Service ==="
echo "Target: $APP_CONTAINER"
echo "Time: $(date -Iseconds)"
echo ""

# Pre-flight
echo "[pre-flight] Container status:"
docker inspect -f '{{.State.Status}}' "$APP_CONTAINER" 2>/dev/null || echo "NOT FOUND"

echo "[pre-flight] Current up{} metric:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=up{job=\"inference-api\"}" | jq '.data.result[0].value[1]' 2>/dev/null || echo "QUERY_FAILED"

# Record start time
START_TS=$(date +%s)
echo ""
echo "[chaos] Killing $APP_CONTAINER at $(date -Iseconds)..."
docker kill "$APP_CONTAINER" 2>/dev/null && echo "Killed." || echo "Container may already be stopped."

# Wait for alert
echo ""
echo "[observe] Waiting ${WAIT_FOR_ALERT}s for ServiceDown alert to fire..."
sleep "$WAIT_FOR_ALERT"

# Check alert state
echo ""
echo "[check] ServiceDown alert status:"
curl -s "$PROMETHEUS_URL/api/v1/query?query=ALERTS{alertname=\"ServiceDown\"}" | jq '.data.result[] | {alertname: .metric.alertname, severity: .metric.severity, state: .value[1]}' 2>/dev/null

echo ""
echo "[check] Alertmanager firing alerts:"
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.status.state == "active") | {alertname: .labels.alertname, startsAt}' 2>/dev/null

# Restore
echo ""
echo "[restore] Restarting $APP_CONTAINER..."
docker restart "$APP_CONTAINER" 2>/dev/null && echo "Container restarted." || echo "Failed to restart. Run: docker compose up -d app"

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))
echo ""
echo "=== Chaos #1 Complete ==="
echo "Total duration: ${DURATION}s"
echo "Metrics to record: time-to-detect (TTD), time-to-mitigate (TTM)"
