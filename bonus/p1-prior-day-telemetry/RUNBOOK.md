# RUNBOOK — Vector Store (Day 19 Retrofit)

**Service:** `vector-store` (Day 19 — ANN retrieval)
**On-call rotation:** SRE + Data team
**SLO:** 99.9% of searches succeed; recall@10 >= 0.90

---

## Alert: `VectorStoreRecallDegradation` (warning)

### What it means
Recall@10 has been below 0.90 for 30+ minutes on a collection. Users get irrelevant results — this is the *silent failure* I most fear. The service returns 200 OK but the answers are wrong.

### Immediate triage (first 5 min)
1. **Open the vector store dashboard** → Grafana → "Vector Store Overview"
2. Check which collection is affected (label `{{ $labels.collection }}`)
3. Look at the "Index Size" panel — did the collection grow rapidly? (>2× in 24h → index fragmentation)
4. Check the "GPU Memory" panel — is the GPU out of memory?
5. Run `curl http://vector-store:8001/stats | jq` to confirm collection sizes

### If index fragmentation
- The collection grew without reindexing. Run: `POST /reindex?collection=<name>` (or restart with `--optimize` flag)
- Expected time-to-resolution: 10–15 min for 1M vectors

### If embedding drift
- Check the drift detection pipeline: `bonus/p3-vn-drift/scripts/drift_pipeline.py`
- If PSI > 0.2 on the embedding distribution: the data going in has shifted → embedding model may need fine-tuning or re-benchmarking
- Consider rolling back to previous model version

### If GPU memory pressure
- Check `nvidia-smi` or the GPU Memory panel
- Reduce `max_index_size` or shard across multiple collections
- Temporary: set `GPU_MEMORY_FRACTION=0.7` and restart

### Escalation (after 15 min)
- **Page Data team** if recall < 0.85 and no obvious infra cause → possible embedding model regression
- **Page Platform team** if GPU memory is the bottleneck and can't be resolved by config change

---

## Alert: `VectorStoreFastBurn` (critical — page immediately)

### What it means
Error rate is 14.4× above normal across both 5m and 1h windows. The error budget for 30 days could be gone in ~2 days. This usually means the service is partially or fully down for a subset of requests.

### Immediate triage
1. `curl http://vector-store:8001/healthz` — is the service reachable?
2. Check Prometheus → `up{job="vector-store"}` — is it 0? → `ServiceDown`
3. Check logs: `docker logs day23-vector-store --tail 100`
4. Look for collection errors: `sum(rate(vector_search_requests_total{status="error"}[5m])) by (collection)`
5. If only one collection is failing → the collection may be corrupted. Try dropping and re-creating.

### Common causes and fixes
| Symptom | Likely cause | Action |
|---------|-------------|--------|
| All collections error | Service crashed / OOM | Restart: `docker restart day23-vector-store` |
| One collection errors | Index file corrupted | `rm -rf /data/indices/<name>` then reindex |
| Intermittent errors | Network/timeout to embedding service | Check embedding service latency dashboard |

---

## Alert: `VectorStoreSlowBurn` (warning — investigate within 1 hour)

### What it means
Sustained 6× burn rate over 30m and 6h windows. Something is degrading slowly — time to investigate during business hours.

### Triage
- Check recent deployments: was the embedding model updated?
- Check upstream data pipeline: are malformed vectors being upserted?
- Run the drift detection notebook to compare today's vectors vs. last week's

---

## Post-recovery

1. Update this runbook if you discovered a new failure mode
2. If the incident lasted > 15 min: write a postmortem in `bonus/p5-chaos-postmortem/postmortems/`
3. Review: did the alert fire early enough? If not, tune the `for` duration or burn-rate window
