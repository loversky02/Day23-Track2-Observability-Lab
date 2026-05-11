# Incident #01 — Complete Inference Service Outage

**Incident ID:** INC-2026-05-11-001
**Severity:** SEV1 — Critical
**Author:** SRE on-call (Chaos exercise)
**Status:** Resolved

---

## 1. Timeline (UTC+7)

| Time | Event |
|------|-------|
| 14:02:00 | `docker kill day23-app` executed — container process terminated |
| 14:02:15 | Prometheus scrape against `:8000/healthz` fails — first missed scrape |
| 14:03:00 | Prometheus `up{job="inference-api"}` transitions 1→0 |
| 14:04:00 | `ServiceDown` alert enters PENDING state (`for: 1m` satisfied) |
| 14:04:00 | Alertmanager receives `ServiceDown` firing alert |
| 14:04:10 | Alertmanager dispatches to Slack `#general` (after `group_wait: 10s`) |
| 14:04:12 | **TIME-TO-DETECT (TTD): 2 min 12 sec** — SRE sees Slack notification |
| 14:04:30 | SRE acknowledges alert, opens Grafana dashboard |
| 14:05:00 | SRE confirms: `up{job="inference-api"} == 0`, all other services healthy |
| 14:05:30 | SRE checks `docker ps -a` — `day23-app` exited |
| 14:06:00 | SRE checks logs: `docker logs day23-app --tail 20` — no error, just killed |
| 14:07:00 | SRE runs `docker restart day23-app` — container starts |
| 14:07:30 | `up{job="inference-api"}` transitions 0→1 |
| 14:08:00 | `ServiceDown` alert transitions to INACTIVE |
| 14:09:00 | Alertmanager dispatches RESOLVED notification to Slack |
| 14:09:30 | SRE confirms `/healthz` returns 200, `/predict` returns valid response |
| 14:10:00 | **TIME-TO-MITIGATE (TTM): 8 min** — incident resolved |

**Total impact:** ~8 minutes of downtime. 0 requests served during this window.
**Detection latency:** 2 min 12 sec (from kill to Slack notification).

---

## 2. Detection

**Primary signal:** `up{job="inference-api"} == 0`

Prometheus scraped `/metrics` every 15s. After container kill, 3 consecutive scrape failures caused `up` to go 0. The `ServiceDown` alert has `for: 1m`, so the alert fired after 1 minute of sustained `up == 0`.

**What worked well:**
- `ServiceDown` alert caught this perfectly — high signal, no false positives
- Slack notification was immediate (10s group_wait + webhook latency)
- Grafana dashboard showed clear red status

**What could be better:**
- The `for: 1m` added 60s to detection. For a critical user-facing service, this could be `for: 30s` or even `for: 0s` with a 15s scrape interval.
- No automated runbook execution — manual restart required SRE intervention

---

## 3. Mitigation

**Action taken:** `docker restart day23-app`
**Why this worked:** The container was killed but not removed. Restart brought it back with the same configuration.
**Alternative considered:** Rolling back to previous deployment (not needed — config was unchanged).

---

## 4. Root Cause

**Direct cause:** `docker kill` sent SIGKILL to the container process (simulated OOM kill).
**5 Whys analysis:**

1. Why was the service down? → Container process was killed.
2. Why was the container killed? → Simulated OOM kill (in production: kernel OOM killer or accidental `docker stop`).
3. Why didn't it auto-restart? → The container's restart policy was not `always` or `unless-stopped`.
4. Why wasn't restart policy set? → `docker-compose.yml` does not specify `restart: always` for the `app` service.
5. Why wasn't this caught in review? → Lab environment — restart policy was deemed unnecessary for development.

---

## 5. Action Items

| # | Action | Owner | Priority | Status |
|---|--------|-------|----------|--------|
| 1 | Add `restart: unless-stopped` to `app` service in docker-compose.yml | SRE | P0 | ✅ DONE — applied in this commit |
| 2 | Add `restart: unless-stopped` to all 7 core services | SRE | P1 | ✅ DONE |
| 3 | Reduce `ServiceDown` `for` from `1m` to `30s` for faster detection | SRE | P1 | ✅ DONE — updated ai-quality.yml |
| 4 | Create liveness probe with auto-heal: if `up == 0` for 2m → auto-restart via webhook | SRE | P2 | Backlog |
| 5 | Add container restart count metric: `rate(container_restarts_total[1h])` panel to dashboard | SRE | P2 | Backlog |

---

## 6. Lessons Learned

- **Detection was fast** (2 min) because `ServiceDown` is the simplest, most reliable alert. Every service needs this.
- **Mitigation was manual.** For a 2 AM page, automated restart would save 5-7 minutes and let the on-call stay in bed.
- **The `for: 1m` debate:** Fast enough for lab, but production user-facing services should consider `for: 30s` with `group_wait: 5s`.
- **No data loss** — Prometheus metrics from before the kill were preserved in TSDB.
