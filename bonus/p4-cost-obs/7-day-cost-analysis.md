# 7-Day LLM Cost Analysis

**Period:** 2026-05-04 → 2026-05-10 (simulated from Day 23 lab traffic pattern)
**Budget:** $500/month ($16.67/day sustainable)
**Models used:** gpt-4o, gpt-4o-mini, claude-sonnet-4, llama-3.1-70b (self-hosted)

---

## Daily Cost Breakdown

| Day | gpt-4o | gpt-4o-mini | claude-sonnet-4 | llama-3.1-70b | Total |
|-----|--------|-------------|-----------------|---------------|-------|
| Mon | $8.42  | $1.20       | $3.15           | $0.00         | $12.77 |
| Tue | $7.89  | $1.05       | $2.98           | $0.00         | $11.92 |
| Wed | $15.33 | $3.42       | $5.67           | $0.00         | $24.42 |
| Thu | $6.50  | $0.95       | $2.30           | $0.00         | $9.75  |
| Fri | $9.87  | $1.50       | $3.80           | $0.00         | $15.17 |
| Sat | $3.20  | $0.45       | $1.10           | $0.00         | $4.75  |
| Sun | $2.80  | $0.38       | $0.95           | $0.00         | $4.13  |
| **Total** | **$54.01** | **$8.95** | **$19.95** | **$0.00** | **$82.91** |

**7-day burn rate:** $82.91 → forecast $355/month (under $500 budget, 29% headroom)

---

## Top 3 Most Expensive Endpoints

### 1. `/chat/completions` on gpt-4o — $54.01 (65.2%)
**Why expensive:** All complex reasoning tasks routed here. Average 850 input + 400 output tokens/request.
**Saving opportunity:** 40% of these requests are simple classification/ summarization → route to gpt-4o-mini.
**Estimated savings:** $21.60/week → $93.60/month.

### 2. `/chat/completions` on claude-sonnet-4 — $19.95 (24.1%)
**Why expensive:** Used for long-form content generation. Average 2200 output tokens/request.
**Saving opportunity:** Add `max_tokens=1024` cap for internal tool calls (not user-facing).
**Estimated savings:** $8.00/week → $34.70/month.

### 3. `/chat/completions` on gpt-4o-mini — $8.95 (10.8%)
**Why cheap:** Already the cost-efficient choice. No action needed.

---

## Cost Anomaly: Wednesday Spike

Wednesday shows a spike ($24.42 vs avg $11.84):
- **Root cause:** Debug session — developer ran 45 test prompts with `gpt-4o` at full context window
- **Detection:** `LLMPerRequestCostAnomaly` alert would have fired at 3:15 PM (P99 cost = $0.85 vs baseline $0.12)
- **Prevention:** Add `max_tokens=256` for non-production environments, use gpt-4o-mini for tests

---

## #1 Cost-Saving Recommendation: Semantic Cache

**Implement semantic caching** (e.g., GPTCache or Redis with embedding similarity):
- Cache responses for prompts with > 0.95 cosine similarity
- Estimated cache hit rate: 20-30% for production traffic
- **Savings:** $60-90/month (15-20% of total spend)
- **Implementation effort:** ~4 hours (Redis + sentence-transformer for similarity)
- **Payback period:** < 1 week at current burn rate

---

## Model Mix Recommendation

| Task type | Current model | Recommended | Savings |
|-----------|-------------|-------------|---------|
| Simple Q&A | gpt-4o | gpt-4o-mini | 94% |
| Summarization | gpt-4o | gpt-4o-mini | 94% |
| Code generation | claude-sonnet-4 | claude-haiku-3.5 | 73% |
| Complex reasoning | gpt-4o | gpt-4o (keep) | 0% |
| Internal classification | gpt-4o | Self-host llama-3.1-8b | ~100% |

**If all recommendations implemented:** $355/month → ~$190/month (46% reduction)
