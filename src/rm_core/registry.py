"""Find implementations by name through Python entry points.

A component registers its adapters in its own pyproject.toml, e.g.

    [project.entry-points."airm.kv_transports"]
    p2p = "hetero_p2p.airm:P2PTransport"

and a runtime loads one by name from configuration: `registry.load("airm.kv_transports", "p2p")`.
"""
from __future__ import annotations

import sys
from importlib import metadata
from typing import Dict, List

GROUPS = {
    "airm.accelerator_providers": "AcceleratorProvider",
    "airm.kv_transports": "KVTransport",
    "airm.placements": "Placement",
    "airm.workloads": "workload runner (see PROTOCOL.md §5.3)",
}


def _entry_points(group: str):
    eps = metadata.entry_points()
    if sys.version_info >= (3, 10):
        return list(eps.select(group=group))
    return list(eps.get(group, []))


def available(group: str) -> Dict[str, str]:
    """name -> 'module:object' for every registered implementation in `group`."""
    if group not in GROUPS:
        raise KeyError(f"unknown group {group!r}; known: {sorted(GROUPS)}")
    return {ep.name: ep.value for ep in _entry_points(group)}


def load(group: str, name: str, **kwargs):
    """Instantiate the implementation registered as `name` in `group`."""
    for ep in _entry_points(group):
        if ep.name == name:
            return ep.load()(**kwargs)
    raise KeyError(f"no {group} implementation named {name!r}; available: {sorted(available(group))}")


def groups() -> List[str]:
    return list(GROUPS)
