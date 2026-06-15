from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TranslumeBaseModel(BaseModel):
    """Base model for Translume schemas.

    Acceptance criteria:
        1. JSON serialization: Models can be serialized through Pydantic.
        2. Explicit fields: Unknown fields are rejected by default.
        3. Immutability: Models are frozen to prevent hidden mutation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
