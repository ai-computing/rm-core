"""L3–L4: what has to run, and where it should run."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from .accelerator import Accelerator
from .errors import ContractError

WORKLOAD_KINDS = ("prefill", "decode", "serve", "train", "embed", "search")
SLO_KEYS = ("ttft_p90_ms", "ttft_p99_ms", "tpot_p90_ms", "tpot_p99_ms", "e2e_p90_ms", "tok_s_min")


@dataclass(frozen=True)
class Workload:
    kind: str
    model: str
    slo: Dict[str, float] = field(default_factory=dict)
    precision: str = "bf16"
    batch_hint: Optional[int] = None
    labels: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> "Workload":
        if self.kind not in WORKLOAD_KINDS:
            raise ContractError(f"Workload.kind {self.kind!r} not in {WORKLOAD_KINDS}")
        unknown = set(self.slo) - set(SLO_KEYS)
        if unknown:
            raise ContractError(f"unknown SLO keys {sorted(unknown)}; allowed {SLO_KEYS}")
        return self


@dataclass(frozen=True)
class PlacementDecision:
    accelerator_ids: List[str]
    kv_transport: str = ""          # transport name for prefill->decode handoff, "" if none
    reason: str = ""                # human-readable; logged and shown in lmd-top


@runtime_checkable
class Placement(Protocol):
    """Chooses accelerators for a workload (entry-point group `airm.placements`).

    Contract (PROTOCOL.md §5): returns only ids from `pool`; deterministic for the same inputs;
    returns an empty decision (not an exception) when nothing fits, with the reason.
    """

    name: str

    def place(self, workload: Workload, pool: Sequence[Accelerator],
              metrics: Optional[Dict[str, float]] = None) -> PlacementDecision: ...
