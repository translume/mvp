from __future__ import annotations


class BlockedRemoteModelProvider:
    """Provider that fails if a remote model route is requested."""

    async def structured_completion(self, **_: object) -> dict[str, object]:
        """Raise because remote model providers are not allowed in MVP mode."""
        raise RuntimeError("remote model providers are blocked in Translume MVP mode")
