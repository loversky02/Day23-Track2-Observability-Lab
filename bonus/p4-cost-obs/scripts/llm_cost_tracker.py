"""LLM Cost Tracker — Instrumented OpenAI-compatible API wrapper.

Emits Prometheus metrics per request: tokens_input, tokens_output, cost_usd, model.
Supports OpenAI, Anthropic (via proxy), vLLM, llama.cpp, and any OpenAI-compatible endpoint.

Usage:
    from llm_cost_tracker import CostTrackedLLM
    llm = CostTrackedLLM(api_key="...", model="gpt-4o")
    response = llm.chat([{"role": "user", "content": "Hello"}])
"""
from __future__ import annotations

import json
import os
import time
import hashlib
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest

# ── Pricing table (USD per 1M tokens) — update monthly ──────────
# Source: openai.com/pricing, anthropic.com/pricing
PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o":              {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":         {"input": 10.00, "output": 30.00},
    "gpt-4":               {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo":       {"input": 0.50,  "output": 1.50},
    "o3-mini":             {"input": 1.10,  "output": 4.40},
    "o1":                  {"input": 15.00, "output": 60.00},
    "o1-mini":             {"input": 1.10,  "output": 4.40},
    # Anthropic (via API proxy — pricing as of 2025)
    "claude-opus-4":       {"input": 15.00, "output": 75.00},
    "claude-sonnet-4":     {"input": 3.00,  "output": 15.00},
    "claude-haiku-3.5":    {"input": 0.80,  "output": 4.00},
    # Google
    "gemini-2.0-flash":    {"input": 0.10,  "output": 0.40},
    "gemini-2.0-pro":      {"input": 1.25,  "output": 5.00},
    # Open-source (self-hosted) — cost is $0 in API fees but GPU time has real cost
    "llama-3.1-70b":       {"input": 0.00,  "output": 0.00},
    "llama-3.1-8b":        {"input": 0.00,  "output": 0.00},
    "qwen-2.5-72b":        {"input": 0.00,  "output": 0.00},
}

# ── Prometheus metrics ───────────────────────────────────────────
_registry = CollectorRegistry()

LLM_REQUESTS = Counter(
    "llm_cost_requests_total",
    "Total LLM API requests",
    ["model", "vendor", "endpoint"],
    registry=_registry,
)
LLM_TOKENS = Counter(
    "llm_cost_tokens_total",
    "Total tokens processed",
    ["model", "vendor", "direction"],
    registry=_registry,
)
LLM_COST = Counter(
    "llm_cost_usd_total",
    "Cumulative cost in USD",
    ["model", "vendor"],
    registry=_registry,
)
LLM_COST_PER_REQUEST = Histogram(
    "llm_cost_per_request_usd",
    "Cost per individual request",
    ["model", "vendor"],
    buckets=(0.0001, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0),
    registry=_registry,
)
LLM_REQUEST_LATENCY = Histogram(
    "llm_request_latency_seconds",
    "LLM API request latency",
    ["model", "vendor"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=_registry,
)
LLM_BUDGET_REMAINING = Gauge(
    "llm_budget_remaining_usd",
    "Remaining monthly budget in USD",
    ["vendor"],
    registry=_registry,
)

# ── Cost Tracker ──────────────────────────────────────────────────

class CostTrackedLLM:
    """Wraps an OpenAI-compatible client with cost tracking.

    Use like:
        llm = CostTrackedLLM(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")
        resp = llm.chat([{"role": "user", "content": "Hello"}])
        print(f"Cost: ${resp['cost_usd']:.6f}")
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        monthly_budget_usd: float = 500.0,
        vendor: str | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "sk-mock")
        self.model = model
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.monthly_budget = monthly_budget_usd

        # Detect vendor from model name
        if vendor:
            self.vendor = vendor
        elif model.startswith("gpt-") or model.startswith("o"):
            self.vendor = "openai"
        elif model.startswith("claude-"):
            self.vendor = "anthropic"
        elif model.startswith("gemini-"):
            self.vendor = "google"
        else:
            self.vendor = "self-hosted"

    def chat(self, messages: list[dict], **kwargs) -> dict:
        """Send chat completion request and track cost.

        Returns: {"content": str, "input_tokens": int, "output_tokens": int,
                   "cost_usd": float, "model": str, "latency_ms": float}
        """
        import urllib.request

        start = time.perf_counter()
        endpoint = kwargs.get("endpoint", "chat/completions")

        # Build request payload
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 256),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False,
        }
        if "stop" in kwargs:
            payload["stop"] = kwargs["stop"]

        # Make API call
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
        except Exception as e:
            LLM_REQUESTS.labels(model=self.model, vendor=self.vendor, endpoint=endpoint).inc()
            raise

        # Extract usage
        usage = result.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        content = result["choices"][0]["message"]["content"]

        latency = time.perf_counter() - start
        cost = self._compute_cost(input_tokens, output_tokens)

        # Emit metrics
        LLM_REQUESTS.labels(model=self.model, vendor=self.vendor, endpoint=endpoint).inc()
        LLM_TOKENS.labels(model=self.model, vendor=self.vendor, direction="input").inc(input_tokens)
        LLM_TOKENS.labels(model=self.model, vendor=self.vendor, direction="output").inc(output_tokens)
        LLM_COST.labels(model=self.model, vendor=self.vendor).inc(cost)
        LLM_COST_PER_REQUEST.labels(model=self.model, vendor=self.vendor).observe(cost)
        LLM_REQUEST_LATENCY.labels(model=self.model, vendor=self.vendor).observe(latency)

        # Update budget gauge
        total_spent = LLM_COST.labels(model=self.model, vendor=self.vendor)._value.get()
        LLM_BUDGET_REMAINING.labels(vendor=self.vendor).set(
            max(0, self.monthly_budget - total_spent)
        )

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "model": self.model,
            "vendor": self.vendor,
            "latency_ms": round(latency * 1000, 2),
        }

    def _compute_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on pricing table."""
        pricing = PRICING.get(self.model)
        if pricing is None:
            # Unknown model — estimate conservatively
            pricing = {"input": 5.0, "output": 20.0}

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def get_current_spend(self) -> dict[str, float]:
        """Get spend summarized by model."""
        result = {}
        for model in PRICING:
            metric = LLM_COST.labels(model=model, vendor=self.vendor)
            # Access collected value from Prometheus client internals
            samples = metric.collect()
            for s in samples:
                for sample in s.samples:
                    if sample.name.endswith("_total"):
                        result[model] = round(sample.value, 4)
        return result


# ── Metrics endpoint helper ──────────────────────────────────────

def get_cost_metrics() -> bytes:
    """Return Prometheus text format for all cost metrics."""
    return generate_latest(_registry)


# ── Self-test / demo ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== LLM Cost Tracker — Self-Test ===\n")

    # Simulate a day of real-world usage
    import random

    rng = random.Random(42)
    models = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4", "llama-3.1-70b"]
    endpoints = ["chat/completions", "chat/completions", "chat/completions", "chat/completions"]

    total_spend = 0.0
    for i in range(200):
        model = rng.choice(models)
        # 90% small requests, 8% medium, 2% large (debug loops, retry storms)
        tier = rng.choices(["small", "medium", "large"], weights=[90, 8, 2])[0]
        if tier == "small":
            in_toks, out_toks = rng.randint(50, 200), rng.randint(20, 100)
        elif tier == "medium":
            in_toks, out_toks = rng.randint(500, 1500), rng.randint(200, 800)
        else:
            in_toks, out_toks = rng.randint(3000, 8000), rng.randint(1000, 4000)

        # Simulate metrics
        vendor = "openai" if model.startswith("gpt") else ("anthropic" if model.startswith("claude") else "self-hosted")
        LLM_REQUESTS.labels(model=model, vendor=vendor, endpoint="chat/completions").inc()
        LLM_TOKENS.labels(model=model, vendor=vendor, direction="input").inc(in_toks)
        LLM_TOKENS.labels(model=model, vendor=vendor, direction="output").inc(out_toks)

        # Compute cost
        pricing = PRICING.get(model, {"input": 5.0, "output": 20.0})
        cost = (in_toks / 1_000_000) * pricing["input"] + (out_toks / 1_000_000) * pricing["output"]
        LLM_COST.labels(model=model, vendor=vendor).inc(cost)
        LLM_COST_PER_REQUEST.labels(model=model, vendor=vendor).observe(cost)
        LLM_REQUEST_LATENCY.labels(model=model, vendor=vendor).observe(rng.uniform(0.3, 5.0))

        total_spend += cost

    print(f"Total simulated spend: ${total_spend:.4f}")
    print(f"Total requests: 200")
    print()

    # Show per-model breakdown
    print("Per-model breakdown:")
    for model in models:
        samples = list(LLM_COST.labels(model=model, vendor="openai" if model.startswith("gpt") else "anthropic").collect())
        if samples:
            for s in samples:
                for sample in s.samples:
                    if sample.name.endswith("_total"):
                        print(f"  {model:25s}  ${sample.value:.4f}")

    print(f"\nMetrics endpoint would serve: {len(generate_latest(_registry))} bytes")
    print("Done. Run with 'python llm_cost_tracker.py' to see metrics.")
