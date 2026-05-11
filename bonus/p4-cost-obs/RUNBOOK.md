# RUNBOOK — LLM Cost Observability

## Alert: `LLMBudgetBurnRate` (critical)

**What:** Current burn rate forecasts monthly spend > $500 budget.
**Impact:** If unchecked, budget exhausted in < 30 days. Real money being burned.

### Triage (5 min)
1. Open cost dashboard → "Cost by Model" panel → identify biggest spender
2. Check "Cost Per Request P99" → is it a few large requests or many small ones?
3. Run: `sum(increase(llm_cost_usd_total[1h])) by (model)` in Prometheus

### Common causes & fixes
| Pattern | Cause | Fix |
|---------|-------|-----|
| One model 80%+ spend | Users defaulting to expensive model | Switch default to gpt-4o-mini for simple tasks |
| P99 cost spiking | Debug loops, tool recursion | Add `max_tokens=512` cap, early-stop after 3 tool calls |
| Night spike | Cron job / batch processing | Use cheaper model for batch (gpt-4o-mini instead of gpt-4o) |
| Slow steady increase | User growth | Expected — raise budget or implement caching |

### Cost-saving quick wins
1. **Add response caching** — identical prompts within 1h → serve from cache (saves 15-30%)
2. **Model downgrade** — route simple classification/summarization to gpt-4o-mini (96% cheaper)
3. **Prompt compression** — truncate long conversation history to last 10 messages
4. **Batch processing** — group non-urgent requests, use batch API (50% discount)

---

## Alert: `LLMPerRequestCostAnomaly` (warning)

**What:** Per-request P99 cost > 3σ above 1h baseline.

### Triage
1. `topk(5, sum(increase(llm_cost_per_request_usd_bucket[15m])) by (model))`
2. Check recent deployments — did prompt template change grow context?
3. Look for retry storms: `sum(rate(llm_cost_requests_total{status="error"}[15m])) by (model)`

### Leading indicators of runaway cost bugs
- **Loop without early-stop**: agent keeps calling tools → context grows → each subsequent call costs more
- **Retry storm**: failed request retried 3× with full context → 3× cost
- **Prompt-doubling via tool recursion**: tool output appended to prompt → next call double size
- **Streaming leak**: connection not closed → tokens accumulate
