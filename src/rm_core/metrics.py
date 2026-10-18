"""Shared metric names, units and tags. Every component reports with these."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .errors import ContractError

# name -> (unit, kind, description). kind: gauge | summary (percentile already applied) | counter
METRICS: Dict[str, tuple] = {
    "ttft_p50_ms": ("ms", "summary", "time to first token, p50"),
    "ttft_p90_ms": ("ms", "summary", "time to first token, p90"),
    "ttft_p99_ms": ("ms", "summary", "time to first token, p99"),
    "tpot_p50_ms": ("ms", "summary", "time per output token, p50"),
    "tpot_p90_ms": ("ms", "summary", "time per output token, p90"),
    "tpot_p99_ms": ("ms", "summary", "time per output token, p99"),
    "e2e_p90_ms": ("ms", "summary", "end-to-end request latency, p90"),
    "tok_s": ("tokens/s", "gauge", "generated tokens per second, whole system under test"),
    "req_s": ("requests/s", "gauge", "completed requests per second"),
    "power_w": ("W", "gauge", "mean power over the measured window (tag scope=card|node)"),
    "energy_j": ("J", "counter", "energy over the measured window"),
    "gflops_per_w": ("GFLOPS/W", "gauge", "power efficiency"),
    "mfu_pct": ("%", "gauge", "model FLOPs utilization (tag peak_source)"),
    "kv_transfer_ms": ("ms", "summary", "KV handoff time per request"),
    "kv_transfer_gbps": ("GB/s", "gauge", "KV transfer bandwidth"),
    "accuracy_pct": ("%", "gauge", "task accuracy (tag dataset)"),
    "slo_attainment_pct": ("%", "gauge", "requests meeting the SLO"),
    "accelerators": ("count", "gauge", "accelerators in use (tag vendor/model)"),
}
TAG_KEYS = ("component", "model", "accelerator", "vendor", "scope", "peak_source", "dataset",
            "workload", "kv_transport", "run_id", "commit")


@dataclass(frozen=True)
class Measurement:
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def unit(self) -> str:
        return METRICS[self.name][0]

    def validate(self) -> "Measurement":
        if self.name not in METRICS:
            raise ContractError(f"unknown metric {self.name!r}; add it to rm_core.metrics.METRICS first")
        unknown = set(self.tags) - set(TAG_KEYS)
        if unknown:
            raise ContractError(f"unknown tag keys {sorted(unknown)}; allowed {TAG_KEYS}")
        if self.name == "mfu_pct" and "peak_source" not in self.tags:
            raise ContractError("mfu_pct needs tag peak_source (which peak was the denominator)")
        if self.name == "power_w" and self.tags.get("scope") not in ("card", "node"):
            raise ContractError("power_w needs tag scope=card|node")
        if not isinstance(self.value, (int, float)):
            raise ContractError(f"{self.name}: value must be a number")
        return self


def prometheus_name(name: str) -> str:
    """Prometheus series name for a shared metric: airm_<name>."""
    if name not in METRICS:
        raise ContractError(f"unknown metric {name!r}")
    return "airm_" + name
