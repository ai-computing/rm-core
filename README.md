<div align="center">

<h1>rm-core</h1>

<h3>The contracts that connect ai-rm components</h3>

<p>
  <strong>English</strong> · <a href="README.ko.md">한국어</a>
</p>

<p>
  <a href="https://github.com/ai-computing/rm-core/actions/workflows/ci.yml"><img src="https://github.com/ai-computing/rm-core/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/ai-computing/ai-rm"><img src="https://img.shields.io/badge/ai--rm-contracts-7c5cff" alt="ai-rm contracts"></a>
  <a href="PROTOCOL.md"><img src="https://img.shields.io/badge/protocol-v0.1-7c5cff" alt="Protocol v0.1"></a>
  <a href="https://github.com/ai-computing/rm-core/tree/v0.1.1"><img src="https://img.shields.io/badge/rm--core-0.1.1-22d3ee" alt="rm-core 0.1.1"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9%2B-3776ab?logo=python&amp;logoColor=white" alt="Python 3.9+"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/dependencies-none-64748b" alt="No runtime dependencies"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-64748b" alt="License: BSD-3-Clause"></a>
</p>

<p>
  <a href="#-quick-start"><b>Quick start</b></a> ·
  <a href="#-ai-rm-integration"><b>ai-rm integration</b></a> ·
  <a href="#-architecture"><b>Architecture</b></a> ·
  <a href="PROTOCOL.md"><b>Protocol</b></a> ·
  <a href="#-roadmap"><b>Roadmap</b></a>
</p>

</div>

---

**rm-core** is the contracts package of [ai-rm](https://github.com/ai-computing/ai-rm). It defines how
components talk to each other — accelerators (L1), memory tiers and KV transport (L2), workloads and placement
(L3–L4) and the shared metric schema — so that components never import each other. It holds types, interfaces,
reference implementations and conformance checks only: standard library, Python 3.9+, no runtime dependencies.
The normative specification is [PROTOCOL.md](PROTOCOL.md) (v0.1); this is release 0.1.1.

## ✨ Highlights

<table>
<tr>
<td width="33%" valign="top">
<b>Typed contracts per layer</b><br>
<code>Accelerator</code> / <code>AcceleratorProvider</code> (L1), <code>MemoryTier</code> / <code>KVLayout</code> /
<code>KVTransport</code> (L2), <code>Workload</code> / <code>Placement</code> (L3–L4), with validation that raises
<code>ContractError</code>.
</td>
<td width="33%" valign="top">
<b>Selected by name</b><br>
Components register adapters as Python entry points and runtimes load them with
<code>rm_core.registry.load(group, name)</code>, so switching an implementation is a configuration change.
</td>
<td width="33%" valign="top">
<b>Checked by conformance</b><br>
<code>python -m rm_core.conformance</code> runs the contract checks for every registered implementation and reports
PASS, SKIP (no hardware) or FAIL.
</td>
</tr>
<tr>
<td width="33%" valign="top">
<b>One metric language</b><br>
<code>rm_core.metrics.METRICS</code> fixes names, units and tags (TTFT, TPOT, tok/s, power, MFU, KV transfer …);
Prometheus series are named <code>airm_&lt;name&gt;</code>.
</td>
<td width="33%" valign="top">
<b>Kubernetes representation</b><br>
The <code>AcceleratorProfile</code> CRD (<code>airm.ai-computing.io/v1alpha1</code>) and node labels, built and read
back by <code>rm_core.k8s</code>.
</td>
<td width="33%" valign="top">
<b>Reference implementations</b><br>
<code>sim</code>, <code>loopback</code> and <code>greedy</code> need no hardware. They define the expected behavior
and are the shape to copy when writing a real adapter.
</td>
</tr>
</table>

## 🚀 Quick start

```bash
pip install "rm-core @ git+https://github.com/ai-computing/rm-core@v0.1.1"
python -m rm_core.conformance            # check every registered implementation
```

With only rm-core installed, the reference implementations are checked:

```text
PASS  airm.accelerator_providers:sim
PASS  airm.kv_transports:loopback
PASS  airm.placements:greedy
```

Check one group or one implementation: `python -m rm_core.conformance <group> [name ...]`. The command exits
non-zero if any implementation fails.

## 🔌 ai-rm integration

Components implement a contract in a small adapter module inside their own repository and register it under an
entry-point group:

| Entry-point group | Contract | Registered by | Reference |
|---|---|:-:|---|
| `airm.accelerator_providers` | `AcceleratorProvider` | L1 (device discovery) | `sim` |
| `airm.kv_transports` | `KVTransport` | L2 (data movement) | `loopback` |
| `airm.placements` | `Placement` | L4 (placement policy) | `greedy` |
| `airm.workloads` | workload runner ([§5.3](PROTOCOL.md#53-workload-runners)) | L3 (serving, training) | — |

### Implementing a contract

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

Runtimes then select it by name from configuration (`kvTransport: p2p`):

```python
from rm_core import registry
transport = registry.load("airm.kv_transports", "p2p")
```

Reference implementations to copy from: `rm_core.reference` (`SimAcceleratorProvider`, `LoopbackTransport`,
`GreedyPlacement`). Components depend on rm-core with a compatible pin, e.g. `rm-core>=0.1,<0.2`
([§1](PROTOCOL.md#1-scope-and-versioning)).

<details>
<summary><b>Key rules from the protocol</b></summary>
<br>

- **Accelerators** — `id` is `<node>/<vendor>:<index>`, stable across restarts. `peak_tflops` is dense peak per
  precision and needs a `peak_source`; unknown values are omitted, never zero. `discover()` returns `[]` (not an
  exception) when no device is present.
- **KV transport** — `plan()` validates its inputs and raises `TransportError`; `wait()` returns only when the
  data is visible at the destination; a transport never silently falls back to another path. Transports that
  need real devices implement `conformance_case()` and raise `rm_core.conformance.NoHardware` when they are
  absent (reported as SKIP).
- **Placement** — returns only ids from the pool, is deterministic, and returns an empty decision with a
  `reason` (not an exception) when nothing fits.
- **Metrics** — the quantities in `METRICS` are reported under exactly those names and units; tags come from
  `TAG_KEYS`; `mfu_pct` carries `peak_source`, `power_w` carries `scope=card|node`.
- **Security** — contracts, profiles, metrics and logs never carry internal addresses, credentials, tokens or
  keys; site values come from the environment.

Full text: [PROTOCOL.md](PROTOCOL.md).
</details>

<details>
<summary><b>Shared metrics (<code>rm_core.metrics.METRICS</code>)</b></summary>
<br>

| Name | Unit | Meaning |
|---|---|---|
| `ttft_p50_ms` · `ttft_p90_ms` · `ttft_p99_ms` | ms | time to first token |
| `tpot_p50_ms` · `tpot_p90_ms` · `tpot_p99_ms` | ms | time per output token |
| `e2e_p90_ms` | ms | end-to-end request latency, p90 |
| `tok_s` | tokens/s | generated tokens per second, whole system under test |
| `req_s` | requests/s | completed requests per second |
| `power_w` | W | mean power over the measured window (tag `scope=card\|node`) |
| `energy_j` | J | energy over the measured window |
| `gflops_per_w` | GFLOPS/W | power efficiency |
| `mfu_pct` | % | model FLOPs utilization (tag `peak_source`) |
| `kv_transfer_ms` | ms | KV handoff time per request |
| `kv_transfer_gbps` | GB/s | KV transfer bandwidth |
| `accuracy_pct` | % | task accuracy (tag `dataset`) |
| `slo_attainment_pct` | % | requests meeting the SLO |
| `accelerators` | count | accelerators in use (tag `vendor`/`model`) |

Prometheus series: `airm_<name>` (`rm_core.metrics.prometheus_name`). Tag keys: `component`, `model`,
`accelerator`, `vendor`, `scope`, `peak_source`, `dataset`, `workload`, `kv_transport`, `run_id`, `commit`.
</details>

## 🏗 Architecture

```text
src/rm_core/
├── accelerator.py   # L1: Accelerator, AcceleratorProvider; vendor, memory, precision, interconnect enums
├── memory.py        # L2: MemoryTier, KVLayout, TransferPlan/Handle/Result, KVTransport
├── workload.py      # L3–L4: Workload, PlacementDecision, Placement; workload kinds, SLO keys
├── placement.py     # L4: airm-placement document (decisions.json): model, validate(), build()
├── metrics.py       # METRICS, TAG_KEYS, Measurement, prometheus_name
├── k8s.py           # AcceleratorProfile objects and node labels; from_profile()
├── registry.py      # entry-point groups: available(), load(), groups()
├── reference.py     # sim / loopback / greedy (no hardware)
├── conformance.py   # python -m rm_core.conformance
└── errors.py        # ContractError, TransportError, NoHardware
k8s/acceleratorprofile.crd.yaml   # AcceleratorProfile CRD (airm.ai-computing.io/v1alpha1)
k8s/airm-placement.schema.json    # JSON Schema of the airm-placement document (PROTOCOL §5.4)
```

A node daemon publishes each device as a cluster-scoped `AcceleratorProfile` plus summary node labels
`airm.ai-computing.io/<vendor>.<model>=<count>` and `airm.ai-computing.io/managed=true`; `rm_core.k8s` builds both
and reads them back. Profiles never contain addresses or credentials.

## 🧪 Development

```bash
pip install -e .
python -m unittest discover -s tests -v
```

CI runs the tests on Python 3.9–3.12, then `python -m rm_core.conformance` and `python tools/check_sensitive.py .`
([workflow](.github/workflows/ci.yml)).

## 🗺 Roadmap

- [x] Protocol v0.1: contracts, `AcceleratorProfile` CRD, reference implementations, conformance checks
- [x] 0.1.1: `AcceleratorProfile` keeps `extra`, `NoHardware` reported as SKIP under `python -m`, metric migration rule
- [x] 0.1.2 (unreleased): `airm-placement` document normative (§5.4), `rm_core.placement` validator, JSON Schema,
      placement conformance validates the document
- [ ] Protocol v0.2: `MemoryRegion` (owner, fd/offset, size) in transfer plans, so device-to-device transports
      can bind live buffers and pass conformance with a hardware fixture
- [ ] Protocol v0.2: formalized workload-runner interface (`airm.workloads`)

Change log: [PROTOCOL.md § Change log](PROTOCOL.md#change-log).

## 📚 Documentation

| | |
|---|---|
| **Specification** | [PROTOCOL.md](PROTOCOL.md) · [AcceleratorProfile CRD](k8s/acceleratorprofile.crd.yaml) · [placement schema](k8s/airm-placement.schema.json) |
| **ai-rm** | [Umbrella](https://github.com/ai-computing/ai-rm) · [Interfaces](https://github.com/ai-computing/ai-rm/blob/master/docs/interfaces.md) · [Integration guide](https://github.com/ai-computing/ai-rm/blob/master/docs/integration-guide.md) |

## 📄 License

[BSD-3-Clause](LICENSE).

<div align="center"><sub>Part of <a href="https://github.com/ai-computing/ai-rm">ai-rm</a> · ai-computing team · ETRI</sub></div>
