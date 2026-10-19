class ContractError(ValueError):
    """A value violates an rm-core contract (wrong unit, unknown kind, missing field)."""


class TransportError(RuntimeError):
    """A KV transfer failed. Implementations raise this instead of silently falling back."""


class NoHardware(RuntimeError):
    """An adapter's conformance_case() cannot run here (devices absent); reported as SKIP.

    Defined here (not in rm_core.conformance) so that the class is the same object whether the
    checks run as `python -m rm_core.conformance` (module __main__) or are imported.
    """
