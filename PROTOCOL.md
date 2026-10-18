# ai-rm Protocol v0.1

This document is the normative definition of the contracts between ai-rm components. The code
(`src/rm_core`) and the conformance checks (`python -m rm_core.conformance`) implement it; where
they disagree, open an issue — the checks are what CI enforces.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 1. Scope and versioning

- Protocol versions are `MAJOR.MINOR`. A component declares the version it implements in
  `ai-rm.yaml` (`protocol: "0.1"`). Within a major version, minor versions only add optional
  fields, metrics, enum values or entry-point groups.
- While the major version is 0, a minor bump MAY break compatibility; the change log says how.
- Components MUST depend on `rm-core` with a compatible pin (e.g. `rm-core>=0.1,<0.2`).

## 2. How components connect

Components do not import each other. They implement contracts from `rm_core` in a small adapter
module inside their own repo and register it as a Python entry point:

| entry-point group | contract | registered by |
|---|---|---|
| `airm.accelerator_providers` | `AcceleratorProvider` | L1 (device discovery) |
| `airm.kv_transports` | `KVTransport` | L2 (data movement) |
| `airm.placements` | `Placement` | L4 (placement policy) |
| `airm.workloads` | workload runner (§5.3) | L3 (serving, training) |

```toml
[project.entry-points."airm.kv_transports"]
p2p = "hetero_p2p.airm:P2PTransport"
```

Runtimes select implementations **by name from configuration** (`kvTransport: p2p`), via
`rm_core.registry.load(group, name)`. An adapter MUST be constructible with no arguments or with
keyword arguments documented in the component's README; it MUST NOT read site values (addresses,
credentials) from anywhere but the environment.

`rm-core` ships reference implementations — `sim`, `loopback`, `greedy` — that need no hardware.
They define the expected behavior and back the simulated cluster.

## 3. Accelerators (L1)

`Accelerator` describes one device.

- `id` MUST be `<node>/<vendor>:<index>`, stable across restarts of the provider.
- `vendor`, `memory_kind`, keys of `peak_tflops`, and `interconnect` MUST use the enumerations in
  `rm_core.accelerator`. New values are added to rm-core first.
- `peak_tflops` is dense peak per precision. If set, `peak_source` MUST say where the number comes
  from (datasheet, measured, or an explicit assumption). Unknown values MUST be omitted, never zero.
- `AcceleratorProvider.discover()` MUST return validated accelerators, MUST be stable across calls,
  and MUST return `[]` (not raise) when no device is present.

### 3.1 Kubernetes representation

A node daemon publishes each device as a cluster-scoped `AcceleratorProfile`
(`airm.ai-computing.io/v1alpha1`, CRD in `k8s/`) and summary node labels
`airm.ai-computing.io/<vendor>.<model>=<count>` and `airm.ai-computing.io/managed=true`.
`rm_core.k8s` builds both; consumers read them back with `from_profile()`.
Profiles MUST NOT contain addresses or credentials.

## 4. Memory tiers and KV transport (L2)

`MemoryTier` is a place KV data can live (`device-hbm`, `device-dram`, `host-dram`, `unified`,
`remote`); device tiers carry `accelerator_id`. `KVLayout` is the physical KV layout on one side.

A `KVTransport`:

1. `supports(src, dst)` MUST be cheap and side-effect free.
2. `plan(...)` MUST validate its inputs and raise `TransportError` (or `ContractError`) for an
   unsupported pair, an empty/negative token range, or layouts it cannot move. Layout or dtype
   conversion is the model adapter's job, not the transport's, unless the transport documents it.
   `plan.nbytes` MUST equal `tokens × src_layout.bytes_per_token()`.
3. `submit(plan)` MAY return before the copy completes.
4. `wait(handle, timeout_s)` MUST return only when the data is visible at the destination
   (completion fence), with `ok=True`, bytes moved and elapsed seconds — or `ok=False` with an error.
   Waiting a handle twice MUST raise `TransportError`.
5. A transport MUST NOT silently fall back to another path (e.g. host staging when P2P fails).
   Choosing a fallback is the caller's decision, made by name.
6. A transport that needs real devices SHOULD implement `conformance_case()` returning
   `(src_tier, dst_tier, layout)` present on the machine, and raise
   `rm_core.conformance.NoHardware` when they are absent (reported as SKIP, not FAIL).
7. Every completed transfer SHOULD be reported as `kv_transfer_ms` (and MAY as `kv_transfer_gbps`)
   with tag `kv_transport=<name>`.

## 5. Workloads and placement (L3–L4)

### 5.1 Workload

`Workload.kind` is one of `prefill`, `decode`, `serve`, `train`, `embed`, `search`. SLO keys are
limited to `rm_core.workload.SLO_KEYS`.

### 5.2 Placement

`Placement.place(workload, pool, metrics=None)`:
- MUST return only accelerator ids from `pool`,
- MUST be deterministic for the same inputs,
- MUST return an empty decision with a `reason` (not raise) when nothing fits,
- SHOULD name the KV transport to use between prefill and decode in `kv_transport`.

The placement controller runs this policy over `AcceleratorProfile`s and live metrics, and writes
its decisions where the llm-d EPP scorer and serving pods read them (see ai-rm docs).

### 5.3 Workload runners

Serving and training components register a runner under `airm.workloads`. In v0.1 a runner is any
callable that accepts a `Workload` plus keyword configuration and starts the work; its required
configuration keys MUST be documented in the component's README. The runner MUST select its KV
transport by name (`kv_transport=`), never by hard-coded import. (Formalized in v0.2.)

## 6. Metrics

- Components MUST report the quantities listed in `rm_core.metrics.METRICS` under exactly those
  names and units, and MUST NOT report the same quantity under another name.
- Tags MUST come from `TAG_KEYS`. `mfu_pct` MUST carry `peak_source`; `power_w` MUST carry
  `scope=card|node`.
- Prometheus series MUST be named `airm_<name>` (`rm_core.metrics.prometheus_name`).
- The same names are used in research reports (`report.py --metric`) and MLflow, so a
  benchmark, a dashboard and a KPI table refer to the same quantity.
- A new metric is added to `METRICS` (minor protocol bump) before any component reports it.

## 7. Security

Contracts, profiles, metrics and logs MUST NOT carry internal addresses, credentials, tokens or
keys. Site values come from the environment (`cluster.local.env`), never from code or config in git.

## 8. Conformance

`python -m rm_core.conformance [group [name ...]]` loads every registered implementation (or the
named ones) and runs the checks for its group. A component is conformant when its adapters pass,
its tests pass, and `check_sensitive.py` reports clean. Each component's CI SHOULD run the checks
against its own entry points.

## Change log

- 0.1 (2026-10): first version — Accelerator/AcceleratorProvider, MemoryTier/KVLayout/KVTransport,
  Workload/Placement, Metrics, AcceleratorProfile CRD, reference implementations, conformance.
