from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


class VendorRuntimeError(RuntimeError):
    """Raised when a vendored runtime cannot execute."""


REMOTE_MODEL_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "NVIDIA_API_KEY",
)


def add_vendor_repo_to_path(repo_path: Path) -> None:
    """Add a vendored Python repository to `sys.path`.

    Acceptance criteria:
        1. Missing repository raises `VendorRuntimeError`.
        2. Adds repo root and src directory when present.
        3. Does not add duplicate path entries.
        4. Does not import any package.

    Args:
        repo_path: Vendored repository root.

    Raises:
        VendorRuntimeError: If `repo_path` is missing or empty.
    """
    if not repo_path.exists() or not repo_path.is_dir():
        raise VendorRuntimeError(f"vendored repository is missing: {repo_path}")
    if not any(repo_path.iterdir()):
        raise VendorRuntimeError(f"vendored repository is empty: {repo_path}")
    candidates = [repo_path, repo_path / "src"]
    for candidate in candidates:
        if candidate.exists():
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)


def import_vendor_module(repo_path: Path, module_names: tuple[str, ...]) -> Any:
    """Import the first available module name from a vendored repository.

    Acceptance criteria:
        1. Adds repository import paths before import.
        2. Tries module names in caller-provided order.
        3. Raises `VendorRuntimeError` when no module imports.
        4. Does not mask the repository path in error messages.

    Args:
        repo_path: Vendored repository root.
        module_names: Candidate module names.

    Returns:
        Imported module object.

    Raises:
        VendorRuntimeError: If no module can be imported.
    """
    add_vendor_repo_to_path(repo_path)
    errors: list[str] = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ImportError as error:
            errors.append(f"{module_name}: {error}")
    raise VendorRuntimeError(
        f"no expected module imported from {repo_path}: {'; '.join(errors)}"
    )


def assert_remote_model_env_blocked(
    *,
    allow_local_openai: bool = False,
) -> None:
    """Reject remote model-provider environment configuration.

    Acceptance criteria:
        1. Blocks known remote model API keys when present.
        2. Allows local OpenAI-compatible vLLM only when explicitly requested.
        3. Does not mutate environment variables.

    Args:
        allow_local_openai: Whether OPENAI_API_KEY may be set for local vLLM.

    Raises:
        VendorRuntimeError: If remote model credentials are configured.
    """
    blocked = []
    for key in REMOTE_MODEL_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if not value:
            continue
        if allow_local_openai and key == "OPENAI_API_KEY":
            continue
        blocked.append(key)
    if blocked:
        raise VendorRuntimeError(
            "remote model provider environment is not allowed: "
            + ", ".join(sorted(blocked))
        )


def read_json_file(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk.

    Acceptance criteria:
        1. Missing file raises `VendorRuntimeError`.
        2. Non-object JSON raises `VendorRuntimeError`.
        3. Invalid JSON raises `VendorRuntimeError`.

    Args:
        path: JSON file path.

    Returns:
        JSON object.
    """
    if not path.exists():
        raise VendorRuntimeError(f"required JSON config is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise VendorRuntimeError(f"invalid JSON config: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise VendorRuntimeError(f"JSON config must be an object: {path}")
    return payload
