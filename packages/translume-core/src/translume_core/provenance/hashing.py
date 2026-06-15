from __future__ import annotations

import hashlib
import json


def stable_json_hash(value: dict[str, object]) -> str:
    """Return a deterministic SHA-256 hash for JSON-compatible data.

    Acceptance criteria:
        1. Equivalent dictionaries produce the same hash regardless of key order.
        2. Output is a lowercase SHA-256 hex digest.
        3. Function is pure.

    Args:
        value: JSON-compatible dictionary.

    Returns:
        SHA-256 hex digest.
    """
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def hash_text(value: str) -> str:
    """Return a SHA-256 hash of text.

    Acceptance criteria:
        1. Same text returns same digest.
        2. Output is lowercase SHA-256 hex digest.
        3. Function is pure.
    """
    return hashlib.sha256(value.encode()).hexdigest()
