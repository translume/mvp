from __future__ import annotations


class ProviderUnavailableError(RuntimeError):
    """Raised when a required external provider is not configured."""
