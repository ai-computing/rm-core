"""L2: memory tiers and KV-cache movement between them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Tuple, runtime_checkable

from .errors import ContractError

TIER_KINDS = ("device-hbm", "device-dram", "host-dram", "unified", "remote")
KV_DTYPES = ("bf16", "fp16", "fp8", "int8", "dlfloat16")


@dataclass(frozen=True)
class MemoryTier:
    """A place KV data can live. `accelerator_id` is set for device memory, empty for host memory."""

    name: str                       # e.g. "rngd0-hbm", "host-dram", "gb10-unified"
    kind: str
    capacity_bytes: int
    accelerator_id: str = ""

    def validate(self) -> "MemoryTier":
        if self.kind not in TIER_KINDS:
            raise ContractError(f"MemoryTier.kind {self.kind!r} not in {TIER_KINDS}")
        if self.capacity_bytes <= 0:
            raise ContractError("MemoryTier.capacity_bytes must be > 0")
        if self.kind.startswith("device") and not self.accelerator_id:
            raise ContractError("device memory tiers need accelerator_id")
        return self


@dataclass(frozen=True)
class KVLayout:
    """Physical KV layout on one side of a transfer. Token-major unless `order` says otherwise."""

    num_layers: int
    num_kv_heads: int
    head_dim: int
    dtype: str
    block_tokens: int = 1
    order: str = "token-major"      # token-major | head-major | vendor:<name>

    def bytes_per_token(self) -> int:
        size = {"bf16": 2, "fp16": 2, "dlfloat16": 2, "fp8": 1, "int8": 1}[self.dtype]
        return 2 * self.num_layers * self.num_kv_heads * self.head_dim * size   # K and V

    def validate(self) -> "KVLayout":
        if self.dtype not in KV_DTYPES:
            raise ContractError(f"KVLayout.dtype {self.dtype!r} not in {KV_DTYPES}")
        if min(self.num_layers, self.num_kv_heads, self.head_dim, self.block_tokens) <= 0:
            raise ContractError("KVLayout dimensions must be > 0")
        return self


@dataclass(frozen=True)
class TransferPlan:
    request_id: str
    src: MemoryTier
    dst: MemoryTier
    src_layout: KVLayout
    dst_layout: KVLayout
    tokens: Tuple[int, int]         # [start, end)
    nbytes: int
    detail: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TransferHandle:
    request_id: str
    transport: str
    token: str                      # opaque, unique per submit


@dataclass(frozen=True)
class TransferResult:
    request_id: str
    ok: bool
    nbytes: int
    seconds: float
    error: Optional[str] = None


@runtime_checkable
class KVTransport(Protocol):
    """Moves KV cache between memory tiers (entry-point group `airm.kv_transports`).

    Contract (PROTOCOL.md §4): `wait` returns only after the data is visible at the destination
    (completion fence); failures raise TransportError or return ok=False — never a silent fallback
    to another path; a handle is waited at most once.
    """

    name: str

    def supports(self, src: MemoryTier, dst: MemoryTier) -> bool: ...

    def plan(self, request_id: str, src: MemoryTier, dst: MemoryTier, src_layout: KVLayout,
             dst_layout: KVLayout, tokens: Tuple[int, int]) -> TransferPlan: ...

    def submit(self, plan: TransferPlan) -> TransferHandle: ...

    def wait(self, handle: TransferHandle, timeout_s: float) -> TransferResult: ...

    def close(self) -> None: ...
