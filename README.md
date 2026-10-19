# rm-core

The contracts that connect [ai-rm](https://github.com/ai-computing/ai-rm) components:
accelerators (L1), memory tiers and KV transport (L2), workloads and placement (L3–L4), and the
shared metric schema. Types, interfaces, reference implementations and conformance checks only —
standard library, Python 3.9+.

- **Spec**: [PROTOCOL.md](PROTOCOL.md) (v0.1)
- **Kubernetes**: [`k8s/acceleratorprofile.crd.yaml`](k8s/acceleratorprofile.crd.yaml)

```bash
pip install "rm-core @ git+https://github.com/ai-computing/rm-core@v0.1.1"
python -m rm_core.conformance            # check every registered implementation
```

## Implementing a contract

```python
# your_pkg/airm.py
from rm_core import KVTransport, TransferPlan, TransferHandle, TransferResult, TransportError

class P2PTransport:
    name = "p2p"
    def supports(self, src, dst): ...
    def plan(self, request_id, src, dst, src_layout, dst_layout, tokens): ...
    def submit(self, plan): ...
    def wait(self, handle, timeout_s): ...
    def close(self): ...
```

```toml
# your pyproject.toml
[project.entry-points."airm.kv_transports"]
p2p = "your_pkg.airm:P2PTransport"
```

```bash
python -m rm_core.conformance airm.kv_transports p2p
```

Reference implementations to copy from: `rm_core.reference` (`SimAcceleratorProvider`,
`LoopbackTransport`, `GreedyPlacement`).

## Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

BSD-3-Clause.
