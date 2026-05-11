# Incident #02 — Silent Quality Degradation (Model Poisoning)

**Incident ID:** INC-2026-05-11-002
**Severity:** SEV2 — Warning (escalated after 30 min)
**Author:** SRE on-call (Chaos exercise)
**Status:** Resolved — led to dashboard + alert improvement

---

## 1. Timeline (UTC+7)

| Time | Event |
|------|-------|
| 15:00:00 | Chaos script starts — 20% of `/predict` requests injected with `fail=true` |
| 15:00:30 | First poisoned request returns HTTP 503 |
| 15:01:00 | `inference_quality_score` begins dropping (from 0.92 → 0.85 within 2 min) |
| 15:05:00 | Error rate reaches 20%. `SLOFastBurn` condition partially met (5m window > 14.4×) |
| 15:05:30 | `SLOFastBurn` alert FIRES — 5m AND 1h windows both exceed threshold |
| 15:05:45 | Alertmanager dispatches to Slack `#general` |
| 15:06:00 | **SRE sees alert — but the alert says "error budget" not "quality drop"** |
| 15:06:30 | SRE confused: checks latency (normal), checks `up` (1), checks error rate (elevated) |
| 15:08:00 | SRE realizes: errors are NOT random — they're concentrated in specific model |
| 15:08:30 | SRE checks `inference_quality_score` panel — quality = 0.65 (below 0.7 threshold!) |
| 15:10:00 | `InferenceQualityDrop` alert FIRES (after `for: 10m` from start of degradation) |
| 15:10:30 | **TRUE DETECTION: SRE now understands root cause — quality, not just errors** |
| 15:11:00 | SRE checks logs: `forced failure (alert demo)` pattern identified |
| 15:12:00 | SRE identifies source: poisoned requests from chaos script on localhost |
| 15:13:00 | Chaos script stopped |
| 15:15:00 | Quality score begins recovering |
| 15:25:00 | `InferenceQualityDrop` resolves (`for: 10m` with sustained recovery) |
| 15:30:00 | `SLOFastBurn` resolves |

**TTD (true):** 10 min 30 sec — from first poison to `InferenceQualityDrop` alert fire.
**TTD (effective):** 5 min 30 sec — from first poison to SRE seeing `SLOFastBurn` (but unclear).
**TTM:** 13 min — from poison start to chaos script stopped.

---

## 2. Detection

**Primary signal that fired first:** `SLOFastBurn` (5m window) — caught the error rate spike.
**Primary signal that explained what was happening:** `InferenceQualityDrop` — but it fired 5 minutes later due to `for: 10m`.

**The problem:** `SLOFastBurn` told me "something is wrong with error rate" but NOT what or why. The quality score told me "model outputs are degraded" which is the actual failure mode a user cares about. But the quality alert has `for: 10m` — too slow.

**What worked:**
- `SLOFastBurn` is a good catch-all — it fires whenever error rate spikes, regardless of cause
- Quality score (eval-as-metric) correctly detected the degradation

**What failed:**
- `InferenceQualityDrop` `for: 10m` is too long for a fast-degrading model
- The quality score was 0.65 but the alert threshold is 0.70 — should be tighter
- No alert correlated error rate with quality score to distinguish "infra failure" from "model failure"

---

## 3. Mitigation

**Action:** Stopped the chaos script injecting poisoned requests.
**In production equivalent:** Roll back model version, or route traffic away from degraded model.

---

## 4. Root Cause

**Direct cause:** 20% of requests returning HTTP 503 + garbage responses (simulated model degradation).

**5 Whys:**
1. Why did quality drop? → 20% of requests were poisoned with `fail=true`.
2. Why wasn't this caught faster? → Quality alert had `for: 10m` — designed for slow drift, not fast poison.
3. Why was the SRE confused by the first alert? → `SLOFastBurn` signaled "error rate high" but not "model outputs are wrong."
4. Why is there no combined alert? → SLO alerts and quality alerts were designed independently.
5. Why was the quality metric lagging? → `inference_quality_score` is a Gauge set per-request — it only reflects the *latest* request, not a rolling average.

---

## 5. Action Items

| # | Action | Owner | Priority | Status |
|---|--------|-------|----------|--------|
| 1 | **Reduce `InferenceQualityDrop` `for: 10m` → `for: 5m`** | SRE | P0 | ✅ DONE — updated `ai-quality.yml` |
| 2 | **Add rolling average quality panel to dashboard** — `avg_over_time(inference_quality_score[5m])` | SRE | P0 | ✅ DONE — added to `ai-service-overview.json` |
| 3 | **Create composite alert: quality < 0.85 AND error rate > 5%** → page as "Model Degradation (not just infra)" | SRE | P0 | ✅ DONE — new alert `ModelDegradationComposite` added |
| 4 | Change `inference_quality_score` from Gauge to Summary (captures distribution, not just latest value) | Platform | P1 | Backlog |
| 5 | Add per-model quality score panel — `inference_quality_score{model}` — to distinguish which model is degraded | SRE | P1 | ✅ DONE |
| 6 | Wire quality score to drift detection: if PSI > 0.25 AND quality < 0.85 → data drift is the root cause | Data | P2 | Backlog |

---

## 6. What Changed in the System (Real Improvement)

This incident directly led to **3 concrete changes** committed to the repo:

1. **`ai-quality.yml`** — `InferenceQualityDrop` `for` reduced from `10m` to `5m`
2. **`ai-service-overview.json`** — Added "Quality Score (5m rolling avg)" panel next to existing latency panels
3. **New alert `ModelDegradationComposite`** — fires when `quality < 0.85 AND error_rate > 0.05`, with annotation "Model outputs may be degraded. Check quality dashboard before assuming infra issue."

These changes ensure the NEXT time quality degrades (even silently), the alert:
- Fires 5 minutes faster
- Tells the SRE "check quality, not infra"
- Has a dedicated dashboard panel for the investigation

---

## 7. Lessons Learned

- **The scariest failure is the one where `up == 1`, latency is normal, but answers are wrong.** This incident proved that without quality-in-loop alerting, this failure mode is invisible to standard RED/USE metrics.
- **SLO alerts catch symptoms, quality alerts catch causes.** You need both.
- **`for: 10m` on quality alerts is too slow for fast poisoning.** Quality degradation can happen in seconds (bad deploy, poisoned data pipeline). Alert thresholds should distinguish "slow drift" (for: 30m, PSI-based) from "fast poison" (for: 5m, quality-score-based).
