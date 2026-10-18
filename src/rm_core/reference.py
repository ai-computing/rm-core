"""Reference implementations that need no hardware.

Used by the conformance tests, by ai-rm's simulated cluster (`make up-sim`), and as the shape
to copy when writing a real adapter. Registered under the name "sim" / "loopback" / "greedy".
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

from .accelerator import Accelerator
from .errors import TransportError
from .memory import KVLayout, MemoryTier, TransferHandle, TransferPlan, TransferResult
from .workload import PlacementDecision, Workload

# A small heterogeneous node for simulation. Numbers are placeholders, labeled as such.
_SIM_DEVICES = [
    {"vendor": "furiosa", "model": "RNGD", "memory_bytes": 48 << 30, "memory_kind": "hbm",
     "peak_tflops": {"bf16": 256.0}, "interconnect": ["pcie5", "p2p-dma"]},
    {"vendor": "rebellions", "model": "ATOM", "memory_bytes": 16 << 30, "memory_kind": "gddr",
     "peak_tflops": {"fp16": 32.0}, "interconnect": ["pcie5", "p2p-dma"]},
]


class SimAcceleratorProvider:
    """Fake devices. AIRM_SIM_DEVICES (JSON list like _SIM_DEVICES) overrides the default set."""

    name = "sim"

    def __init__(self, node: Optional[str] = None):
        self.node = node or os.environ.get("AIRM_NODE_NAME", "sim-node")

    def discover(self) -> List[Accelerator]:
        specs = json.loads(os.environ["AIRM_SIM_DEVICES"]) if os.environ.get("AIRM_SIM_DEVICES") else _SIM_DEVICES
        out, index = [], {}
        for spec in specs:
            i = index.get(spec["vendor"], 0)
            index[spec["vendor"]] = i + 1
            out.append(Accelerator(id=f"{self.node}/{spec['vendor']}:{i}", node=self.node,
                                   peak_source="simulation placeholder", **spec).validate())
        return out


class LoopbackTransport:
    """Copies KV bytes between in-process buffers. Honors the full KVTransport contract."""

    name = "loopback"

    def __init__(self, fail_request_ids: Sequence[str] = ()):
        self._fail = set(fail_request_ids)
        self._pending: Dict[str, Tuple[TransferPlan, float]] = {}
        self._lock = threading.Lock()
        self.store: Dict[Tuple[str, str], bytes] = {}       # (tier name, request id) -> bytes

    def supports(self, src: MemoryTier, dst: MemoryTier) -> bool:
        return src.name != dst.name

    def plan(self, request_id, src, dst, src_layout: KVLayout, dst_layout: KVLayout, tokens):
        if not self.supports(src, dst):
            raise TransportError(f"{self.name}: cannot move {src.name} -> {dst.name}")
        if src_layout.bytes_per_token() != dst_layout.bytes_per_token():
            raise TransportError(f"{self.name}: layout size mismatch; convert in the model adapter")
        start, end = tokens
        if not 0 <= start < end:
            raise TransportError(f"{self.name}: bad token range {tokens}")
        return TransferPlan(request_id, src.validate(), dst.validate(), src_layout.validate(),
                            dst_layout.validate(), (start, end), (end - start) * src_layout.bytes_per_token())

    def submit(self, plan: TransferPlan) -> TransferHandle:
        token = uuid.uuid4().hex
        with self._lock:
            self._pending[token] = (plan, time.perf_counter())
        return TransferHandle(plan.request_id, self.name, token)

    def wait(self, handle: TransferHandle, timeout_s: float) -> TransferResult:
        with self._lock:
            entry = self._pending.pop(handle.token, None)
        if entry is None:
            raise TransportError(f"{self.name}: unknown or already-waited handle {handle.token}")
        plan, started = entry
        if plan.request_id in self._fail:
            return TransferResult(plan.request_id, False, 0, time.perf_counter() - started, "injected failure")
        self.store[(plan.dst.name, plan.request_id)] = bytes(plan.nbytes)   # data visible before return
        return TransferResult(plan.request_id, True, plan.nbytes, time.perf_counter() - started)

    def close(self) -> None:
        with self._lock:
            self._pending.clear()


class GreedyPlacement:
    """Prefill on the device with the highest peak, decode on the one with the most memory."""

    name = "greedy"

    def place(self, workload: Workload, pool: Sequence[Accelerator],
              metrics: Optional[Dict[str, float]] = None) -> PlacementDecision:
        workload.validate()
        if not pool:
            return PlacementDecision([], reason="empty pool")
        peak = lambda a: max(a.peak_tflops.values()) if a.peak_tflops else 0.0
        if workload.kind == "prefill":
            best = max(pool, key=lambda a: (peak(a), a.id))
        else:
            best = max(pool, key=lambda a: (a.memory_bytes, a.id))
        transport = "loopback" if workload.kind in ("prefill", "decode") else ""
        return PlacementDecision([best.id], transport, f"greedy: {workload.kind} -> {best.model}")
