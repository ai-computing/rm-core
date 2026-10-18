class ContractError(ValueError):
    """A value violates an rm-core contract (wrong unit, unknown kind, missing field)."""


class TransportError(RuntimeError):
    """A KV transfer failed. Implementations raise this instead of silently falling back."""
