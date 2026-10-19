"""L4: the placement document — ConfigMap `airm-placement`, key `decisions.json` (PROTOCOL.md §5.4).

The placement controller writes it; the llm-d EPP scorer, serving pods and lmd-top read it.

    {"protocol": "0.1", "generation": 3, "updatedAt": "2026-10-19T00:00:00Z", "placement": "topology",
     "decisions": [{"pool": "llama8b-pd-pool",
                    "workload": {"kind": "decode", "model": "...", "slo": {...}, "labels": {...}},
                    "acceleratorIds": ["<node>/furiosa:1"], "kvTransport": "shm", "reason": "..."}]}

`validate(doc)` lists every violation (empty list = valid) and ignores unknown fields.
`PlacementDocument` / `Decision` are the typed model; `build()` bumps `generation` only when the
placement or the decisions change. JSON Schema: k8s/airm-placement.schema.json.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from . import PROTOCOL_VERSION
from .accelerator import _ID, PRECISIONS, VENDORS
from .errors import ContractError
from .workload import SLO_KEYS, WORKLOAD_KINDS, PlacementDecision, Workload

CONFIGMAP = "airm-placement"
KEY = "decisions.json"
# Optional workload label: the card type a role was restricted to, `<vendor>.<model>` as in the
# node labels `airm.ai-computing.io/<vendor>.<model>=<count>` (rm_core.k8s.node_labels).
ACCELERATOR_LABEL = "airm.ai-computing.io/accelerator"
PROTOCOL_ANNOTATION = "airm.ai-computing.io/protocol"

_PROTOCOL = re.compile(r"^\d+\.\d+$")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_VENDOR_MODEL = re.compile(r"^([a-z0-9]+)\.([A-Za-z0-9][A-Za-z0-9._-]*)$")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_workload(w, at: str, errors: List[str]) -> None:
    if not isinstance(w, dict):
        errors.append(f"{at}: must be an object")
        return
    if w.get("kind") not in WORKLOAD_KINDS:
        errors.append(f"{at}.kind: {w.get('kind')!r} not in {WORKLOAD_KINDS}")
    if not isinstance(w.get("model"), str) or not w.get("model"):
        errors.append(f"{at}.model: must be a non-empty string")
    slo = w.get("slo", {})
    if not isinstance(slo, dict):
        errors.append(f"{at}.slo: must be an object")
    else:
        for k, v in slo.items():
            if k not in SLO_KEYS:
                errors.append(f"{at}.slo: unknown key {k!r}; allowed {SLO_KEYS}")
            elif not _is_num(v):
                errors.append(f"{at}.slo.{k}: must be a number")
    labels = w.get("labels", {})
    if not isinstance(labels, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items()):
        errors.append(f"{at}.labels: must be an object of strings")
    elif ACCELERATOR_LABEL in labels:
        m = _VENDOR_MODEL.match(labels[ACCELERATOR_LABEL])
        if not m or m.group(1) not in VENDORS:
            errors.append(f"{at}.labels[{ACCELERATOR_LABEL}]: {labels[ACCELERATOR_LABEL]!r} must be "
                          f"'<vendor>.<model>' with vendor in {VENDORS}")
    if "precision" in w and w["precision"] not in PRECISIONS:
        errors.append(f"{at}.precision: {w['precision']!r} not in {PRECISIONS}")
    if w.get("batchHint") is not None and not (_is_int(w["batchHint"]) and w["batchHint"] > 0):
        errors.append(f"{at}.batchHint: must be a positive integer or null")


def _check_decision(d, at: str, errors: List[str]) -> None:
    if not isinstance(d, dict):
        errors.append(f"{at}: must be an object")
        return
    if not isinstance(d.get("pool"), str) or not d.get("pool"):
        errors.append(f"{at}.pool: must be a non-empty string")
    _check_workload(d.get("workload"), f"{at}.workload", errors)
    ids = d.get("acceleratorIds")
    if not isinstance(ids, list):
        errors.append(f"{at}.acceleratorIds: must be a list")
        ids = []
    for i, a in enumerate(ids):
        if not isinstance(a, str) or not _ID.match(a):
            errors.append(f"{at}.acceleratorIds[{i}]: {a!r} must look like '<node>/<vendor>:<index>'")
    if len(ids) != len({repr(a) for a in ids}):
        errors.append(f"{at}.acceleratorIds: duplicate ids {ids}")
    for k in ("kvTransport", "reason"):
        if k in d and not isinstance(d[k], str):
            errors.append(f"{at}.{k}: must be a string")
    if isinstance(d.get("acceleratorIds"), list) and not ids and not d.get("reason"):
        errors.append(f"{at}: empty acceleratorIds needs a reason")
    # The vendor in each id must agree with the card type the role was restricted to.
    labels = (d.get("workload") or {}).get("labels") if isinstance(d.get("workload"), dict) else None
    m = _VENDOR_MODEL.match(labels.get(ACCELERATOR_LABEL, "")) if isinstance(labels, dict) else None
    if m:
        for a in ids:
            if isinstance(a, str) and _ID.match(a) and a.split("/", 1)[1].split(":")[0] != m.group(1):
                errors.append(f"{at}.acceleratorIds: {a!r} is not a {m.group(1)} card ({ACCELERATOR_LABEL})")


def validate(doc) -> List[str]:
    """Every violation of PROTOCOL §5.4 in `doc` (a parsed `decisions.json`); [] when valid.

    Unknown fields are ignored at every level (forward compatibility).
    """
    errors: List[str] = []
    if not isinstance(doc, dict):
        return ["document: must be a JSON object"]
    p = doc.get("protocol")
    if not isinstance(p, str) or not _PROTOCOL.match(p):
        errors.append(f"protocol: {p!r} must be a 'MAJOR.MINOR' string")
    elif p.split(".")[0] != PROTOCOL_VERSION.split(".")[0]:
        errors.append(f"protocol: major version {p!r} is not {PROTOCOL_VERSION}'s")
    gen = doc.get("generation")
    if not _is_int(gen) or gen < 0:
        errors.append(f"generation: {gen!r} must be an integer >= 0")
        gen = None
    if "updatedAt" not in doc:
        errors.append("updatedAt: required (null before the first write)")
    else:
        t = doc["updatedAt"]
        if t is None:
            if gen:
                errors.append("updatedAt: must be set when generation > 0")
        elif not isinstance(t, str) or not _TIME.match(t):
            errors.append(f"updatedAt: {t!r} must be RFC 3339 UTC ('YYYY-MM-DDTHH:MM:SSZ') or null")
    pol = doc.get("placement")
    if pol is not None and (not isinstance(pol, str) or not pol):
        errors.append("placement: must be a non-empty string")
    elif pol is None and gen:
        errors.append("placement: required when generation > 0 (the policy that wrote the decisions)")
    decisions = doc.get("decisions")
    if not isinstance(decisions, list):
        errors.append("decisions: must be a list")
        return errors
    if decisions and gen == 0:
        errors.append("generation: must be > 0 when there are decisions")
    seen = set()
    for i, d in enumerate(decisions):
        _check_decision(d, f"decisions[{i}]", errors)
        if isinstance(d, dict) and isinstance(d.get("workload"), dict):
            key = (d.get("pool"), d["workload"].get("kind"))
            if key in seen:
                errors.append(f"decisions[{i}]: second decision for pool {key[0]!r} kind {key[1]!r}")
            seen.add(key)
    return errors


def _workload_to_dict(w: Workload) -> dict:
    out = {"kind": w.kind, "model": w.model, "slo": dict(w.slo), "labels": dict(w.labels)}
    if w.precision != "bf16":
        out["precision"] = w.precision
    if w.batch_hint is not None:
        out["batchHint"] = w.batch_hint
    return out


def _workload_from_dict(d: dict) -> Workload:
    return Workload(kind=d["kind"], model=d["model"], slo=dict(d.get("slo") or {}),
                    precision=d.get("precision") or "bf16", batch_hint=d.get("batchHint"),
                    labels=dict(d.get("labels") or {}))


@dataclass(frozen=True)
class Decision:
    """One entry of `decisions`: the accelerators one role (`workload.kind`) of one pool got."""

    pool: str
    workload: Workload
    accelerator_ids: List[str] = field(default_factory=list)
    kv_transport: str = ""
    reason: str = ""

    @classmethod
    def from_placement(cls, pool: str, workload: Workload, d: PlacementDecision) -> "Decision":
        return cls(pool, workload, list(d.accelerator_ids), d.kv_transport, d.reason)

    @property
    def decision(self) -> PlacementDecision:
        return PlacementDecision(list(self.accelerator_ids), self.kv_transport, self.reason)

    @property
    def nodes(self) -> List[str]:
        """Nodes of the cards, in order of first appearance (the part of each id before '/')."""
        return list(dict.fromkeys(a.split("/", 1)[0] for a in self.accelerator_ids))

    def to_dict(self) -> dict:
        return {"pool": self.pool, "workload": _workload_to_dict(self.workload),
                "acceleratorIds": list(self.accelerator_ids), "kvTransport": self.kv_transport,
                "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict) -> "Decision":
        return cls(d["pool"], _workload_from_dict(d["workload"]), list(d.get("acceleratorIds") or []),
                   d.get("kvTransport") or "", d.get("reason") or "")


@dataclass(frozen=True)
class PlacementDocument:
    """The value of `airm-placement` / `decisions.json`. The default is the empty v0.1 document."""

    generation: int = 0
    updated_at: Optional[str] = None
    placement: Optional[str] = None
    decisions: List[Decision] = field(default_factory=list)
    protocol: str = PROTOCOL_VERSION

    def validate(self) -> "PlacementDocument":
        errors = validate(self.to_dict())
        if errors:
            raise ContractError("; ".join(errors))
        return self

    def for_pool(self, pool: str) -> List[Decision]:
        return [d for d in self.decisions if d.pool == pool]

    def to_dict(self) -> dict:
        out = {"protocol": self.protocol, "generation": self.generation, "updatedAt": self.updated_at}
        if self.placement is not None:
            out["placement"] = self.placement
        out["decisions"] = [d.to_dict() for d in self.decisions]
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    @classmethod
    def from_dict(cls, doc: dict) -> "PlacementDocument":
        """Raises ContractError listing every violation; unknown fields are dropped."""
        errors = validate(doc)
        if errors:
            raise ContractError("; ".join(errors))
        return cls(doc["generation"], doc["updatedAt"], doc.get("placement"),
                   [Decision.from_dict(d) for d in doc["decisions"]], doc["protocol"])


def parse(cm: Optional[dict]) -> PlacementDocument:
    """The document inside a ConfigMap object; the empty document when the ConfigMap or key is absent."""
    raw = ((cm or {}).get("data") or {}).get(KEY)
    if not raw:
        return PlacementDocument()
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise ContractError(f"{CONFIGMAP}/{KEY}: not JSON ({e})") from None
    return PlacementDocument.from_dict(doc)


def build(decisions: Sequence[Decision], previous: PlacementDocument, placement: str,
          now: Optional[datetime] = None) -> Tuple[PlacementDocument, bool]:
    """The next document and whether it changed. `generation` goes up only on a change of
    `placement` or `decisions`, so an unchanged rewrite wakes no reader."""
    decisions = list(decisions)
    if previous.decisions == decisions and previous.placement == placement:
        return previous, False
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return PlacementDocument(previous.generation + 1, now.strftime("%Y-%m-%dT%H:%M:%SZ"), placement,
                             decisions).validate(), True


def configmap(doc: PlacementDocument, namespace: str, labels: Optional[Dict[str, str]] = None) -> dict:
    """The ConfigMap object to apply in the llm-d namespace (`namespace`)."""
    return {"apiVersion": "v1", "kind": "ConfigMap",
            "metadata": {"name": CONFIGMAP, "namespace": namespace,
                         "labels": {"app.kubernetes.io/part-of": "ai-rm", "airm.ai-computing.io/managed": "true",
                                    **(labels or {})},
                         "annotations": {PROTOCOL_ANNOTATION: doc.protocol}},
            "data": {KEY: doc.validate().to_json()}}


def is_newer(doc: PlacementDocument, applied_generation: Optional[int]) -> bool:
    """Reader rule: apply a document only if its generation is above the last one applied."""
    return applied_generation is None or doc.generation > applied_generation
