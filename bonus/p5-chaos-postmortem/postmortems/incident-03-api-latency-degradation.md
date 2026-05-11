# Incident #03 — Upstream LLM API Latency Degradation

**Incident ID:** INC-2026-05-11-003
**Severity:** SEV2 → SEV1 (escalated after 30 min of sustained burn)
**Author:** SRE on-call (Chaos exercise)
**Status:** Resolved

---

## 1. Timeline (UTC+7)

| Time | Event |
|------|-------|
| 16:00:00 | Network latency (+3000ms ±500ms jitter) injected on OTel Collector port |
| 16:00:15 | Traces begin experiencing 3-3.5s additional delay in span export |
| 16:01:00 | P99 inference latency jumps from 0.3s → 3.5s |
| 16:06:00 | `HighInferenceLatency` alert FIRES (P99 > 2s for 5m) |
| 16:06:30 | Alertmanager dispatches to Slack `#general` |
| 16:07:00 | SRE sees alert, opens latency dashboard |
| 16:07:30 | SRE confirms: P99 high, P50 normal (0.2s) — TAIL LATENCY problem |
| 16:08:00 | SRE checks Jaeger traces — sees 3s gaps between spans (network delay) |
| 16:09:00 | SRE identifies root cause: network latency injection on OTel Collector |
| 16:10:00 | **But wait — latency is on OTel Collector, not on the app itself!** |
| 16:11:00 | SRE realizes: the tracer spans are slow because span export is delayed, not inference |
| 16:11:30 | **FALSE ALARM for inference latency** — the app is fine, telemetry pipeline is slow |
| 16:12:00 | SRE checks: `/predict` response time from client side = 0.25s (normal) |
| 16:12:30 | **Insight: `inference_latency_seconds` histogram is measured INSIDE the span — it's accurate.** Only span export is slow. The alert was real but investigation was misled. |
| 16:15:00 | SRE checks `SLOFastBurn` — not firing (errors are normal, only latency is high) |
| 16:16:00 | SRE checks `SLOSlowBurn` — PENDING (30m window not yet satisfied) |
| 16:25:00 | Latency is sustained high for 25 minutes |
| 16:36:00 | `SLOSlowBurn` alert FIRES (30m AND 6h windows both > 6×) |
| 16:36:30 | Alertmanager dispatches to Slack |
| 16:37:00 | **ESCALATION: SRE now understands this is sustained, not a blip** |
| 16:38:00 | SRE removes tc latency rule — latency drops back to normal |
| 16:40:00 | P99 latency returns to 0.3s |
| 16:46:00 | `HighInferenceLatency` resolves (for: 5m) |
| 16:55:00 | `SLOSlowBurn` resolves |

**TTD:** 6 min (first alert) — 36 min (slow burn confirmation)
**TTM:** 38 min (from injection to mitigation)

---

## 2. Detection

**First alert:** `HighInferenceLatency` at +6 min — fast but could be a transient blip.
**Confirming alert:** `SLOSlowBurn` at +36 min — confirmed this is sustained degradation, not noise.

**What worked:**
- Multi-window alerting did its job: fast alert for immediate awareness, slow burn for confirmation
- The histogram buckets captured tail latency well (0.05 to 10.0)
- Jaeger traces provided immediate visual confirmation of where delay was

**What was confusing:**
- Latency was injected on OTel Collector, not the app. The metric `inference_latency_seconds` was measured correctly (inside the span, before export), but Jaeger showed delayed spans — creating conflicting signals.
- No dashboard panel showing "OTel Collector export latency" vs "Application latency" side-by-side

---

## 3. Mitigation

**Action:** Removed tc network latency rule.
**Production equivalent:** Route traffic to a different LLM API region (e.g., switch from `api.openai.com` to a European endpoint if Southeast Asia is degraded).

**Better approach for production:**
1. Circuit-breaker: if P99 latency > 5s for 3 minutes → automatically fail over to backup model (gpt-4o-mini)
2. Timeout: set `OPENAI_TIMEOUT=10s` (was using default 120s — too long)

---

## 4. Root Cause

**Direct cause:** Simulated 3s network latency on upstream dependency (simulating OpenAI API regional degradation).
**5 Whys:**
1. Why was P99 latency high? → 3s network delay added to every request's dependency call.
2. Why did it take 38 min to mitigate? → SRE spent 5 min investigating the wrong thing (Jaeger trace delay vs actual app latency).
3. Why were there conflicting signals? → No dashboard panel comparing app latency vs telemetry pipeline latency.
4. Why no automatic failover? → Circuit breaker not implemented for LLM API dependency.
5. Why is the timeout 120s? → Default OpenAI SDK timeout was never overridden.

---

## 5. Action Items

| # | Action | Owner | Priority | Status |
|---|--------|-------|----------|--------|
| 1 | **Add "OTel Collector export latency" panel** to dashboard — `rate(otelcol_exporter_sent_spans[1m])` + histogram of export duration | SRE | P0 | ✅ DONE |
| 2 | **Reduce OpenAI SDK timeout** from 120s → 15s via env var `OPENAI_TIMEOUT` | SRE | P0 | ✅ DONE |
| 3 | **Add circuit-breaker alert:** if `HighInferenceLatency` fires → auto-check if it's app or dependency → runbook step #1 now says "check if OTel Collector or app" | SRE | P1 | Backlog |
| 4 | **Create latency attribution dashboard:** breakout inference time vs network wait vs token generation time (using span events already in traces) | SRE | P2 | Backlog |
| 5 | **Implement automated failover:** if P99 > 5s for 5 min → route 50% traffic to backup model | Platform | P2 | Backlog |
| 6 | Add `inference_latency_seconds` by phase: embed, search, generate — already traced as child spans, not yet as separate histograms | SRE | P2 | Backlog |

---

## 6. System Change Resulting from This Incident

Added a new panel to the AI Service Overview dashboard:
- **"Latency Attribution"** — shows `inference_latency_seconds` broken down by `span.name` (embed-text, vector-search, generate-tokens)
- This allows SRE to see in 5 seconds whether latency is in the model (generate-tokens) or in preprocessing (embed-text)

Also modified `HighInferenceLatency` alert description to include:
> "Check Jaeger trace breakdown: is latency in generate-tokens (model slow) or embed-text (preprocessing)? If spans show network gaps, check OTel Collector or upstream API."

---

## 7. Lessons Learned

- **Tail latency is a leading indicator of dependency degradation.** Even though the app was healthy, the 3s dependency delay would eventually cause client timeouts.
- **Multi-window burn-rate alerting prevented over-reaction.** The fast alert said "look", the slow burn said "this is real." Without the slow burn confirmation, this could have been dismissed as a transient blip.
- **Telemetry pipeline latency masquerading as app latency is a real failure mode.** Always compare: app-measured latency vs client-observed latency vs span export latency.
- **38 minutes to mitigate a simulated incident is too long.** For a real SEV1, target < 15 min TTM. The gap was in diagnosis (conflicting signals) not in action.
