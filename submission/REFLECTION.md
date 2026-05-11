# Day 23 Lab Reflection

> Fill in each section. Grader reads the "What I'd change" paragraph closest.

**Student:** loversky
**Submission date:** 2026-05-11
**Lab repo URL:** https://github.com/loversky02/Day23-Track2-Observability-Lab

---

## 1. Hardware + setup output

Paste output of `python3 00-setup/verify-docker.py`:

```
Docker:        OK  (29.4.3)
Compose v2:    OK  (5.1.3)
RAM available: 37.85 GB (OK)
Ports free:    OK
Report written: /home/loversky/Desktop/code/vinai/Day23-Track2-Observability-Lab/00-setup/setup-report.json
```

---

## 2. Track 02 — Dashboards & Alerts

### 6 essential panels (screenshot)

Drop `submission/screenshots/dashboard-overview.png`.

### Burn-rate panel

Drop `submission/screenshots/slo-burn-rate.png`.

### Alert fire + resolve

| When | What | Evidence |
|---|---|---|
| _T0_ | killed `day23-app`         | screenshot `alertmanager-firing.png` |
| _T0+90s_ | `ServiceDown` fired   | screenshot `slack-firing.png` |
| _T1_ | restored app              | — |
| _T1+60s_ | alert resolved        | screenshot `slack-resolved.png` |

### One thing surprised me about Prometheus / Grafana

The SLO burn-rate alert math was surprisingly subtle. The double-window approach (fast burn at 5m+1h, slow burn at 30m+6h) means you need BOTH windows exceeding the threshold simultaneously before paging. This prevents false positives from brief error spikes while still catching genuine budget exhaustion fast enough for a 99.5% SLO. The recording rules that pre-compute failure ratios per window are the real workhorses — without them, the PromQL for the alert expression would be unreadable.

---

## 3. Track 03 — Tracing & Logs

### One trace screenshot from Jaeger

Drop `submission/screenshots/jaeger-trace.png` showing `embed-text → vector-search → generate-tokens` spans.

### Log line correlated to trace

```
{"model": "llama3-mock", "input_tokens": 4, "output_tokens": 43, "quality": 0.795, "duration_seconds": 0.2815, "trace_id": "4ccf55ac7671ac3f5f0cd1263a1aaa8f", "event": "prediction served", "level": "info", "timestamp": "2026-05-11T01:47:58.047950Z"}
```

This log line's `trace_id` field links directly to the Jaeger trace showing the full `predict → embed-text → vector-search → generate-tokens` call chain. The structured JSON format (via structlog) makes it queryable in Loki by `trace_id`, `model`, or `quality`.

### Tail-sampling math

With the composite policy:
- **keep-errors**: 100% of traces with `status_code=ERROR` (~1% of traffic in production)
- **keep-slow**: 100% of traces with latency >2s (~1% of traffic)
- **probabilistic-1pct**: 1% of all remaining healthy traces (~98% of traffic)

Total retention: `1% (errors) + 1% (slow) + 0.01 × 98% (healthy) ≈ 2.98%` of all traces.

At 100 traces/sec, that's ~3 traces/sec retained and ~97 traces/sec dropped. The decision wait of 30s with a 50,000 trace buffer provides ample headroom — the buffer would only fill at ~1,666 traces/sec, well beyond lab scale.

---

## 4. Track 04 — Drift Detection

### PSI scores

```json
{
  "prompt_length": {
    "psi": 3.461,
    "kl": 1.7982,
    "ks_stat": 0.702,
    "ks_pvalue": 0.0,
    "drift": "yes"
  },
  "embedding_norm": {
    "psi": 0.0187,
    "kl": 0.0324,
    "ks_stat": 0.052,
    "ks_pvalue": 0.133853,
    "drift": "no"
  },
  "response_length": {
    "psi": 0.0162,
    "kl": 0.0178,
    "ks_stat": 0.056,
    "ks_pvalue": 0.086899,
    "drift": "no"
  },
  "response_quality": {
    "psi": 8.8486,
    "kl": 13.5011,
    "ks_stat": 0.941,
    "ks_pvalue": 0.0,
    "drift": "yes"
  }
}
```

### Which test fits which feature?

- **`prompt_length`** — **KS test** in production. PSI caught the drift (3.461) but KS provides the p-value (0.0) for statistical significance. Prompt length is a continuous numeric feature where distribution shape matters (users suddenly sending much longer prompts). KS is non-parametric and handles the mean shift from 50→85 cleanly.

- **`embedding_norm`** — **PSI** for monitoring. This feature is stable (no drift expected), so PSI's interpretable thresholds (PSI < 0.1 = no drift, 0.1-0.2 = moderate, > 0.2 = significant) make a good canary. If PSI exceeds 0.1 here, something is wrong with the embedding model.

- **`response_length`** — **KL divergence**. Response length follows a roughly normal distribution. KL divergence is sensitive to distribution shape changes and naturally handles the continuous domain without binning artifacts that can affect PSI at bin boundaries.

- **`response_quality`** — **PSI + KS combined**. Quality scores are bounded [0,1] with a Beta distribution. The shift from Beta(8,2) to Beta(2,6) is drastic (PSI=8.85, KS=0.94). PSI gives the business-readable "population stability" story while KS provides the statistical rigor. In practice, I'd alert on PSI > 0.2 AND KS p-value < 0.01 to avoid false positives from sample size noise.

---

## 5. Track 05 — Cross-Day Integration

### Which prior-day metric was hardest to expose? Why?

Day 18 (Spark) was the hardest to expose credibly. Unlike Qdrant or llama.cpp which have clean /metrics endpoints, Spark's metrics come through the Spark UI JSON API or a StatsD sink — both require either running a real Spark cluster or building a non-trivial stub that mimics the internal metrics registry. The other days (16 cloud node_exporter, 17 Airflow statsd, 19 Qdrant, 20 llama.cpp, 22 DPO evals) all map naturally to Prometheus scrape targets. Day 18 needs an intermediate bridge (Spark → StatsD → Prometheus) that introduces latency and cardinality management concerns. For the cross-day dashboard, Day 18 was left as a stub panel showing "No Data" with a note about the required bridge.

---

## 6. The single change that mattered most

> **Grader reads this closest.** What one thing about your stack design — a metric you added, a label you dropped, a panel you reorganized, an alert threshold you tuned — made the biggest difference between "works" and "useful"? Write 1-2 paragraphs. Connect it to a concept from the deck.

The single change that mattered most was fixing the OpenTelemetry span hierarchy — changing `tracer.start_span("predict")` to `tracer.start_as_current_span("predict")` so that child spans (`embed-text`, `vector-search`, `generate-tokens`) properly inherit the parent's trace context. Before this fix, each span appeared as an isolated one-span trace in Jaeger, making end-to-end latency attribution impossible. After the fix, a single trace in Jaeger shows the full 4-span waterfall — you can immediately see that `generate-tokens` dominates the 200ms request, that `embed-text` is sub-millisecond, and that no span is unexpectedly slow. This connects directly to **§6 (Tracing + OTel + Sampling)** from the deck: "a trace without proper parent-child linkage is just a pile of spans — the hierarchy IS the diagnostic value."

The second insight was that the fix rippled through the entire observability pipeline. The OTel Collector's tail-sampling operates on whole traces, not individual spans — with broken hierarchy, sampling decisions were made per-span rather than per-trace, violating the "all-or-nothing" invariant that makes tail-sampling statistically sound. The structured log line's `trace_id` field (checkpoint #15) also became meaningful only after this fix: correlating a log line to a trace requires the trace to actually contain all its spans. One line of code changed the diagnostic value of the entire stack from "I can see individual operations" to "I can trace a user request end-to-end, from the FastAPI route through embedding, vector search, token generation, and back — with metrics, logs, and traces all connected by the same trace_id."
