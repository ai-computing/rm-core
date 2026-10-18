"""Conformance checks: the acceptance test every adapter must pass.

    python -m rm_core.conformance                         # check everything registered
    python -m rm_core.conformance airm.kv_transports p2p  # check one implementation

Each check takes an instance and raises AssertionError with a specific message on violation.
Hardware-backed adapters can pass `tiers=`/`layout=` that exist on the machine; by default the
checks use small synthetic values so they also run in CI without accelerators.
"""
from __future__ import annotations

import sys
from typing import Callable, Dict, List, Optional, Tuple

from . import registry
from .accelerator import Accelerator, AcceleratorProvider
from .errors import ContractError, TransportError
from .memory import KVLayout, KVTransport, MemoryTier, TransferResult
from .metrics import Measurement
from .workload import Placement, PlacementDecision, Workload


class NoHardware(RuntimeError):
    """Raised by an adapter's conformance_case() when the devices it needs are not on this machine."""


def check_accelerator_provider(provider) -> List[Accelerator]:
    assert isinstance(provider, AcceleratorProvider), "missing name/discover()"
    assert isinstance(provider.name, str) and provider.name, "provider.name must be a non-empty string"
    found = provider.discover()
    assert isinstance(found, list), "discover() must return a list"
    ids = [a.id for a in found]
    assert len(ids) == len(set(ids)), f"duplicate accelerator ids: {ids}"
    for a in found:
        assert isinstance(a, Accelerator), f"discover() returned {type(a).__name__}, not Accelerator"
        a.validate()
    assert [a.id for a in provider.discover()] == ids, "discover() must be stable across calls"
    return found


def check_kv_transport(transport, tiers: Optional[Tuple[MemoryTier, MemoryTier]] = None,
                       layout: Optional[KVLayout] = None) -> None:
    assert isinstance(transport, KVTransport), "missing one of name/supports/plan/submit/wait/close"
    # A hardware transport MAY offer conformance_case() -> (src, dst, layout) for tiers present on
    # this machine, or raise rm_core.conformance.NoHardware to be reported as SKIP.
    if tiers is None and hasattr(transport, "conformance_case"):
        src, dst, layout = transport.conformance_case()
    else:
        src, dst = tiers or (MemoryTier("conf-src", "host-dram", 1 << 30), MemoryTier("conf-dst", "host-dram", 1 << 30))
    layout = layout or KVLayout(num_layers=2, num_kv_heads=2, head_dim=8, dtype="bf16")
    if not transport.supports(src, dst):
        raise AssertionError(f"{transport.name} does not support the test tiers; implement conformance_case()")
    plan = transport.plan("conf-1", src, dst, layout, layout, (0, 16))
    assert plan.nbytes == 16 * layout.bytes_per_token(), "plan.nbytes must equal tokens * bytes_per_token"
    handle = transport.submit(plan)
    assert handle.transport == transport.name and handle.request_id == "conf-1", "handle identity mismatch"
    result = transport.wait(handle, timeout_s=30.0)
    assert isinstance(result, TransferResult) and result.ok, f"transfer failed: {getattr(result, 'error', result)}"
    assert result.nbytes == plan.nbytes and result.seconds >= 0, "result must report bytes moved and time"
    try:
        transport.wait(handle, timeout_s=1.0)
    except TransportError:
        pass
    else:
        raise AssertionError("waiting the same handle twice must raise TransportError")
    for bad in [(16, 16), (-1, 4)]:
        try:
            transport.plan("conf-bad", src, dst, layout, layout, bad)
        except (TransportError, ContractError):
            continue
        raise AssertionError(f"plan() accepted an invalid token range {bad}")
    transport.close()


def check_placement(placement, pool: Optional[List[Accelerator]] = None) -> None:
    from .reference import SimAcceleratorProvider
    assert isinstance(placement, Placement), "missing name/place()"
    pool = pool or SimAcceleratorProvider("conf-node").discover()
    ids = {a.id for a in pool}
    for kind in ("prefill", "decode"):
        w = Workload(kind=kind, model="conformance-model", slo={"tpot_p90_ms": 100})
        d1, d2 = placement.place(w, pool), placement.place(w, pool)
        assert isinstance(d1, PlacementDecision), "place() must return a PlacementDecision"
        assert set(d1.accelerator_ids) <= ids, f"placed outside the pool: {d1.accelerator_ids}"
        assert d1 == d2, "place() must be deterministic for the same inputs"
    empty = placement.place(Workload(kind="decode", model="m"), [])
    assert empty.accelerator_ids == [] and empty.reason, "empty pool -> empty decision with a reason"


def check_measurements(measurements: List[Measurement]) -> None:
    for m in measurements:
        m.validate()


CHECKS: Dict[str, Callable] = {
    "airm.accelerator_providers": check_accelerator_provider,
    "airm.kv_transports": check_kv_transport,
    "airm.placements": check_placement,
}


def main(argv: List[str]) -> int:
    targets = []
    if argv:
        group = argv[0]
        names = argv[1:] or sorted(registry.available(group))
        targets = [(group, n) for n in names]
    else:
        for group in CHECKS:
            targets += [(group, n) for n in sorted(registry.available(group))]
    failed = 0
    for group, name in targets:
        try:
            CHECKS[group](registry.load(group, name))
            print(f"PASS  {group}:{name}")
        except NoHardware as e:
            print(f"SKIP  {group}:{name}: {e}")
        except Exception as e:  # report every failure, keep going
            failed += 1
            print(f"FAIL  {group}:{name}: {type(e).__name__}: {e}")
    if not targets:
        print("no registered implementations found")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
