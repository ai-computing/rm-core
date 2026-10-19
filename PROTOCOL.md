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
its decisions to the placement document (§5.4), where the llm-d EPP scorer, serving pods and
lmd-top read them.

### 5.3 Workload runners

Serving and training components register a runner under `airm.workloads`. In v0.1 a runner is any
callable that accepts a `Workload` plus keyword configuration and starts the work; its required
configuration keys MUST be documented in the component's README. The runner MUST select its KV
transport by name (`kv_transport=`), never by hard-coded import. (Formalized in v0.2.)

### 5.4 Placement document (`airm-placement`, document version 0.1)

The hand-off between the placement controller (writer) and its readers is one JSON document.
`rm_core.placement` implements it (`validate(doc)`, `PlacementDocument`, `build`, `parse`,
`configmap`); `k8s/airm-placement.schema.json` is the JSON Schema for the structure. The document
version is the `protocol` field and follows the protocol version (§1).

**Location.** ConfigMap `airm-placement` in the namespace of the llm-d InferencePools it describes
(the llm-d namespace, e.g. `llm-serving`), key `decisions.json`, value a UTF-8 JSON object. Writers
MUST NOT put decisions under other keys. The ConfigMap SHOULD carry the annotation
`airm.ai-computing.io/protocol: "<version>"` and the label `app.kubernetes.io/part-of: ai-rm`.

```json
{
  "protocol": "0.1",
  "generation": 3,
  "updatedAt": "2026-10-19T00:00:00Z",
  "placement": "topology",
  "decisions": [
    {"pool": "llama8b-pd-pool",
     "workload": {"kind": "prefill", "model": "meta-llama/Llama-3.1-8B-Instruct",
                  "slo": {"tpot_p90_ms": 100},
                  "labels": {"airm.ai-computing.io/accelerator": "furiosa.RNGD"}},
     "acceleratorIds": ["<node>/furiosa:0"], "kvTransport": "shm", "reason": "highest peak"},
    {"pool": "llama8b-pd-pool",
     "workload": {"kind": "decode", "model": "meta-llama/Llama-3.1-8B-Instruct",
                  "slo": {"tpot_p90_ms": 100},
                  "labels": {"airm.ai-computing.io/accelerator": "furiosa.RNGD"}},
     "acceleratorIds": ["<node>/furiosa:1"], "kvTransport": "shm", "reason": "most memory"}
  ]
}
```

| Field | Rule |
|---|---|
| `protocol` | REQUIRED. `"MAJOR.MINOR"`, the protocol version the writer implements |
| `generation` | REQUIRED. Integer ≥ 0; `0` only for the empty document |
| `updatedAt` | REQUIRED. RFC 3339 UTC (`YYYY-MM-DDTHH:MM:SSZ`) time of the last change; `null` only when `generation` is 0 |
| `placement` | Name of the `airm.placements` policy that produced the decisions. REQUIRED when `generation` > 0 |
| `decisions` | REQUIRED. List, empty in the empty document |
| `decisions[].pool` | REQUIRED. InferencePool name (= the EPP's `--pool-name`) |
| `decisions[].workload` | REQUIRED. `Workload` in camelCase: `kind` and `model` REQUIRED; `slo` (keys from `SLO_KEYS`), `labels` (strings), `precision`, `batchHint` OPTIONAL |
| `decisions[].workload.kind` | The role. A prefill/decode pool has one `prefill` and one `decode` decision; an aggregated pool (any role) has one `serve` decision |
| `decisions[].workload.labels["airm.ai-computing.io/accelerator"]` | OPTIONAL. Card type the role was restricted to, `<vendor>.<model>` as in the node labels (§3.1). When set, every card in `acceleratorIds` MUST be of that vendor |
| `decisions[].acceleratorIds` | REQUIRED. Card references: `Accelerator.id`s `<node>/<vendor>:<index>` (= `AcceleratorProfile.spec.id`), no duplicates. The node of a card is the part before `/` |
| `decisions[].kvTransport` | `airm.kv_transports` name for the prefill→decode hand-off; `""` or absent if none |
| `decisions[].reason` | Human-readable. REQUIRED (non-empty) when `acceleratorIds` is empty, which means nothing fits |

The empty document, valid before the first placement, is
`{"protocol": "0.1", "generation": 0, "updatedAt": null, "decisions": []}`.

Writers:
- MUST write only documents that `rm_core.placement.validate` accepts.
- MUST write at most one decision per (`pool`, `workload.kind`).
- MUST increase `generation` by at least one whenever `placement` or `decisions` change, and MUST
  NOT decrease it. A writer SHOULD NOT rewrite a document whose `placement` and `decisions` are
  unchanged; if it does, it MUST keep the same `generation`.
- MUST NOT put addresses or credentials in the document (§7): cards are referenced by id only and
  resolved through `AcceleratorProfile`s.

Readers:
- MUST ignore fields they do not know, at every level, and MUST accept a newer minor `protocol`
  with the same major version.
- MUST NOT apply a document whose `generation` is not greater than the last one they applied
  (`rm_core.placement.is_newer`); equal generations have equal content.
- MUST behave as if the ConfigMap did not exist when it is absent, when `decisions` is empty, or
  when it has no decision for their pool.
- SHOULD treat a document that fails validation as absent and report it, not crash.

## 6. Metrics

- Components MUST report the quantities listed in `rm_core.metrics.METRICS` under exactly those
  names and units, and MUST NOT report the same quantity under another name.
- Tags MUST come from `TAG_KEYS`. `mfu_pct` MUST carry `peak_source`; `power_w` MUST carry
  `scope=card|node`.
- Prometheus series MUST be named `airm_<name>` (`rm_core.metrics.prometheus_name`).
- The same names are used in research reports (`report.py --metric`) and MLflow, so a
  benchmark, a dashboard and a KPI table refer to the same quantity.
- A new metric is added to `METRICS` (minor protocol bump) before any component reports it.
- Migration: a component that already emitted a quantity under its own name MAY keep that series
  for one more minor protocol version, marked deprecated in its README, while consumers move to the
  `airm_` name. Consumers SHOULD read the `airm_` series first and fall back to the old one.

## 7. Security

Contracts, profiles, metrics and logs MUST NOT carry internal addresses, credentials, tokens or
keys. Site values come from the environment (`cluster.local.env`), never from code or config in git.

## 8. Conformance

`python -m rm_core.conformance [group [name ...]]` loads every registered implementation (or the
named ones) and runs the checks for its group. For `airm.placements` the checks include that the
policy's decisions make a valid placement document (§5.4). A component is conformant when its adapters pass,
its tests pass, and `check_sensitive.py` reports clean. Each component's CI SHOULD run the checks
against its own entry points.

## Change log

- 0.1.2 (2026-10-19, rm-core patch; protocol stays 0.1): §5.4 makes the `airm-placement` document
  normative as already written by rm-controller and hetero-llm-d and read by lmd-top (no field
  changed). `rm_core.placement` (typed model, stdlib validator, `build` with the generation rule),
  `k8s/airm-placement.schema.json`, and the `airm.placements` conformance check now also validates
  the document made from a policy's decisions.

- 0.1.1 (2026-10-19, rm-core patch; protocol stays 0.1): `AcceleratorProfile` keeps `extra`
  (CRD field added) and the provider check now verifies the profile round-trip; `NoHardware` moved to
  `rm_core.errors` so `python -m rm_core.conformance` reports SKIP correctly; §6 migration rule.
- Known gap, planned for 0.2: `KVTransport.plan()` carries tiers and layouts but no handle to the
  live buffers. Device-to-device transports (hetero-npu-p2p) need owner-provided buffers, so they
  bind them out of band (`bind(request_id, ...)`) and cannot PASS conformance without a hardware
  fixture. 0.2 adds a `MemoryRegion` (owner, fd/offset, size) to plans.

- 0.1 (2026-10): first version — Accelerator/AcceleratorProvider, MemoryTier/KVLayout/KVTransport,
  Workload/Placement, Metrics, AcceleratorProfile CRD, reference implementations, conformance.
