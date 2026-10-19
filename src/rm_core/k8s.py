"""How L1 information appears in Kubernetes: node labels and AcceleratorProfile objects.

The node daemon (rm_abstract_layer) writes these; the placement controller, EPP scorer and
lmd-top read them. CRD: k8s/acceleratorprofile.crd.yaml.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from .accelerator import Accelerator

GROUP = "airm.ai-computing.io"
VERSION = "v1alpha1"
LABEL_PREFIX = GROUP + "/"


def node_labels(accelerators: List[Accelerator]) -> Dict[str, str]:
    """Summary labels for a node, e.g. airm.ai-computing.io/furiosa.RNGD=2."""
    labels = {LABEL_PREFIX + "managed": "true"}
    for (vendor, model), n in Counter((a.vendor, a.model) for a in accelerators).items():
        labels[f"{LABEL_PREFIX}{vendor}.{model}"] = str(n)
    return labels


def accelerator_profile(acc: Accelerator) -> dict:
    """An AcceleratorProfile object for one device (cluster-scoped, name derived from id)."""
    acc.validate()
    name = acc.id.replace("/", ".").replace(":", "-").lower()
    return {
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "AcceleratorProfile",
        "metadata": {"name": name, "labels": {LABEL_PREFIX + "node": acc.node,
                                              LABEL_PREFIX + "vendor": acc.vendor}},
        "spec": {
            "id": acc.id, "node": acc.node, "vendor": acc.vendor, "model": acc.model,
            "memoryBytes": acc.memory_bytes, "memoryKind": acc.memory_kind,
            "peakTflops": {k: str(v) for k, v in acc.peak_tflops.items()}, "peakSource": acc.peak_source,
            "powerLimitW": None if acc.power_limit_w is None else str(acc.power_limit_w),
            "interconnect": list(acc.interconnect),
            "extra": {k: str(v) for k, v in acc.extra.items()},
        },
    }


def from_profile(obj: dict) -> Accelerator:
    s = obj["spec"]
    return Accelerator(
        id=s["id"], node=s["node"], vendor=s["vendor"], model=s["model"],
        memory_bytes=int(s["memoryBytes"]), memory_kind=s["memoryKind"],
        peak_tflops={k: float(v) for k, v in (s.get("peakTflops") or {}).items()},
        peak_source=s.get("peakSource", ""),
        power_limit_w=float(s["powerLimitW"]) if s.get("powerLimitW") else None,
        interconnect=list(s.get("interconnect") or []),
        extra=dict(s.get("extra") or {}),
    ).validate()
