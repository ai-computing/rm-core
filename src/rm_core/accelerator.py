"""L1: what an accelerator is and what it can do."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable

from .errors import ContractError

VENDORS = ("nvidia", "furiosa", "rebellions", "cpu", "amd", "intel", "other")
MEMORY_KINDS = ("hbm", "gddr", "dram", "unified", "lpddr")
PRECISIONS = ("fp32", "tf32", "bf16", "fp16", "fp8", "int8", "int4")
INTERCONNECTS = ("pcie3", "pcie4", "pcie5", "p2p-dma", "nvlink", "nvlink-c2c", "rdma", "cxl")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9]+:\d+$")


@dataclass(frozen=True)
class Accelerator:
    """One device. `id` is "<node>/<vendor>:<index>" and is stable across restarts.

    Numbers are what the vendor states unless `peak_source` says otherwise; never fill in a value
    you don't have (leave it out) — consumers treat a missing value as unknown, not zero.
    """

    id: str
    vendor: str
    model: str
    memory_bytes: int
    memory_kind: str
    peak_tflops: Dict[str, float] = field(default_factory=dict)   # precision -> dense TFLOPS
    peak_source: str = ""                                        # where peak_tflops comes from
    power_limit_w: Optional[float] = None
    interconnect: List[str] = field(default_factory=list)
    node: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> "Accelerator":
        if not _ID.match(self.id):
            raise ContractError(f"Accelerator.id {self.id!r} must look like '<node>/<vendor>:<index>'")
        if self.vendor not in VENDORS:
            raise ContractError(f"Accelerator.vendor {self.vendor!r} not in {VENDORS}")
        if self.memory_kind not in MEMORY_KINDS:
            raise ContractError(f"Accelerator.memory_kind {self.memory_kind!r} not in {MEMORY_KINDS}")
        if self.memory_bytes <= 0:
            raise ContractError("Accelerator.memory_bytes must be > 0")
        for p, v in self.peak_tflops.items():
            if p not in PRECISIONS or v <= 0:
                raise ContractError(f"peak_tflops[{p!r}]={v!r}: precision must be in {PRECISIONS}, value > 0")
        if self.peak_tflops and not self.peak_source:
            raise ContractError("peak_source is required when peak_tflops is set (MFU depends on it)")
        for link in self.interconnect:
            if link not in INTERCONNECTS:
                raise ContractError(f"interconnect {link!r} not in {INTERCONNECTS}")
        if self.node and not self.id.startswith(self.node + "/"):
            raise ContractError(f"Accelerator.id {self.id!r} does not start with node {self.node!r}")
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Accelerator":
        return cls(**d).validate()


@runtime_checkable
class AcceleratorProvider(Protocol):
    """Discovers the accelerators on the local node (entry-point group `airm.accelerator_providers`)."""

    name: str

    def discover(self) -> List[Accelerator]:
        """Return validated Accelerators present on this node; [] if none. Must not raise for absence."""
        ...
