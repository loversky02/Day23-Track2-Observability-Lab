"""Combined stubs for Days 16, 17, 18, 22 cross-day dashboard panels.

Each day gets its own HTTP server port:
  Day 16 (node_exporter)  → :9103
  Day 17 (Airflow StatsD)  → :9104
  Day 18 (Spark)           → :9105
  Day 22 (DPO eval)        → :9106
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime

from prometheus_client import Gauge, Histogram, Counter, start_http_server


# ── Day 16 — Cloud node_exporter ─────────────────────────────
def run_day16() -> None:
    cpu = Gauge("node_cpu_seconds_total", "Stub: CPU seconds", ["mode"])
    mem = Gauge("node_memory_MemAvailable_bytes", "Stub: available RAM bytes")
    node_up = Gauge("up", "Node up", ["job"])
    start_http_server(9103)
    node_up.labels(job="node").set(1)
    mem.set(8_500_000_000)
    print("Day 16 (node_exporter) stub on :9103")
    while True:
        cpu.labels(mode="idle").inc(0.15)
        cpu.labels(mode="system").inc(0.02)
        mem.set(8_500_000_000 + random.uniform(-1e9, 1e9))
        time.sleep(15)


# ── Day 17 — Airflow StatsD ──────────────────────────────────
def run_day17() -> None:
    dur = Histogram("airflow_dag_run_duration_seconds", "Stub: DAG run duration", ["dag_id"])
    tasks = Gauge("airflow_task_instances", "Stub: running task instances", ["state"])
    start_http_server(9104)
    tasks.labels(state="running").set(2)
    tasks.labels(state="success").set(12)
    print("Day 17 (Airflow) stub on :9104")
    while True:
        d = random.gauss(15, 5)
        for b in (1, 5, 10, 30, 60):
            dur.labels(dag_id="inference_pipeline").observe(d * (b / 10))
        time.sleep(3)


# ── Day 18 — Spark ───────────────────────────────────────────
def run_day18() -> None:
    active = Gauge("spark_application_active", "Stub: active Spark apps")
    executors = Gauge("spark_executor_count", "Stub: executor count")
    start_http_server(9105)
    active.set(1)
    executors.set(4)
    print("Day 18 (Spark) stub on :9105")
    while True:
        active.set(1 if random.random() < 0.95 else 0)
        executors.set(max(0, 4 + int(random.gauss(0, 0.5))))
        time.sleep(10)


# ── Day 22 — DPO Eval ────────────────────────────────────────
def run_day22() -> None:
    pass_rate = Gauge("day22_dpo_eval_pass_rate", "Stub: DPO eval pass rate")
    win_rate = Gauge("day22_dpo_win_rate", "Stub: DPO win rate vs baseline")
    start_http_server(9106)
    print("Day 22 (DPO eval) stub on :9106")
    while True:
        pass_rate.set(round(random.uniform(0.72, 0.88), 3))
        win_rate.set(round(random.uniform(0.55, 0.70), 3))
        time.sleep(20)


def main() -> None:
    import threading
    for fn in (run_day16, run_day17, run_day18, run_day22):
        t = threading.Thread(target=fn, daemon=True, name=fn.__name__)
        t.start()
        time.sleep(0.3)
    print("All cross-day stubs running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
