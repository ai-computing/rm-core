"""rm-core: the contracts that connect ai-rm components.

Types and interfaces only, standard library only. Components implement these contracts in small
adapters and register them under the entry-point groups in `rm_core.registry`; runtimes pick an
implementation by name from configuration. See PROTOCOL.md.
"""
from .accelerator import Accelerator, AcceleratorProvider
from .errors import ContractError, NoHardware, TransportError
from .memory import KVLayout, KVTransport, MemoryTier, TransferHandle, TransferPlan, TransferResult
from .metrics import METRICS, Measurement, prometheus_name
from .workload import Placement, PlacementDecision, Workload

__version__ = "0.1.2"
PROTOCOL_VERSION = "0.1"

__all__ = [
    "Accelerator", "AcceleratorProvider", "ContractError", "NoHardware", "TransportError", "KVLayout", "KVTransport",
    "MemoryTier", "TransferHandle", "TransferPlan", "TransferResult", "METRICS", "Measurement",
    "prometheus_name", "Placement", "PlacementDecision", "Workload", "PROTOCOL_VERSION",
]
