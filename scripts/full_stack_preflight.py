#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "configs" / "integration" / "full_stack_requirements.json"


class PreflightError(RuntimeError):
    """Raised when full-stack integration prerequisites are not satisfied."""


@dataclass(frozen=True)
class PreflightResult:
    """Summary of validated full-stack prerequisites.

    Attributes:
        checked_items: Names of prerequisites that were checked.
    """

    checked_items: tuple[str, ...]


def load_requirements(path: Path) -> dict[str, Any]:
    """Load full-stack integration requirements.

    Acceptance criteria:
        1. Missing requirements file raises `FileNotFoundError`.
        2. Invalid JSON raises `ValueError`.
        3. Non-object JSON raises `ValueError`.
        4. Returned mapping is caller-owned.

    Args:
        path: Requirements JSON path.

    Returns:
        Parsed requirements mapping.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If the file is invalid or non-object JSON.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("full-stack requirements must be a JSON object")
    return dict(payload)


def env_value(name: str, environment: Mapping[str, str]) -> str:
    """Return a stripped environment value.

    Acceptance criteria:
        1. Missing keys return an empty string.
        2. Leading and trailing whitespace is stripped.
        3. Caller-owned environment is not mutated.

    Args:
        name: Environment variable name.
        environment: Environment mapping.

    Returns:
        Stripped variable value or an empty string.
    """
    return environment.get(name, "").strip()


def validate_required_environment(
    required_names: Sequence[str],
    environment: Mapping[str, str],
) -> tuple[str, ...]:
    """Validate required full-stack environment variables.

    Acceptance criteria:
        1. Every listed variable must be present and non-blank.
        2. Missing variables are reported together.
        3. Function is deterministic and pure.

    Args:
        required_names: Required environment variable names.
        environment: Environment mapping.

    Returns:
        Tuple of checked variable names.

    Raises:
        PreflightError: If any required variable is missing or blank.
    """
    missing = [name for name in required_names if not env_value(name, environment)]
    if missing:
        raise PreflightError(
            "missing required full-stack environment variable(s): "
            + ", ".join(sorted(missing))
        )
    return tuple(required_names)


def validate_report_path(path_text: str) -> Path:
    """Validate the real report PDF used by the full-stack integration test.

    Acceptance criteria:
        1. Path must exist.
        2. Path must be a file.
        3. Path must have a `.pdf` suffix.
        4. Empty files are rejected.

    Args:
        path_text: Report path string.

    Returns:
        Validated report path.

    Raises:
        PreflightError: If the file is invalid.
    """
    path = Path(path_text).expanduser().resolve()
    if not path.exists():
        raise PreflightError(f"integration report does not exist: {path}")
    if not path.is_file():
        raise PreflightError(f"integration report is not a file: {path}")
    if path.suffix.casefold() != ".pdf":
        raise PreflightError(f"integration report must be a PDF: {path}")
    if path.stat().st_size <= 0:
        raise PreflightError(f"integration report is empty: {path}")
    return path


def validate_model_identifier(
    model_id: str,
    disallowed_exact: Sequence[str],
) -> str:
    """Validate that the clinical vLLM model identifier is not a placeholder.

    Acceptance criteria:
        1. Blank model identifiers are rejected.
        2. Exact disallowed values are rejected case-insensitively.
        3. Valid model identifiers are returned unchanged except stripping.
        4. Function is deterministic and pure.

    Args:
        model_id: Candidate vLLM model identifier.
        disallowed_exact: Exact placeholder values from config.

    Returns:
        Stripped model identifier.

    Raises:
        PreflightError: If `model_id` is disallowed.
    """
    stripped = model_id.strip()
    blocked = {item.casefold() for item in disallowed_exact}
    if stripped.casefold() in blocked:
        raise PreflightError(
            "VLLM_MODEL must be a real local/Hugging Face model identifier, "
            f"not {stripped!r}"
        )
    return stripped


def validate_vendor_repositories(root: Path) -> tuple[str, ...]:
    """Validate that vendored Harvard MIMS repositories are present.

    Acceptance criteria:
        1. OptimusKG, ToolUniverse, and Medea directories must exist.
        2. Each directory must contain at least one file.
        3. Function does not import or mutate vendor repositories.

    Args:
        root: Repository root.

    Returns:
        Tuple of validated vendor repository names.

    Raises:
        PreflightError: If any vendor repository is missing or empty.
    """
    vendor_names = ("OptimusKG", "ToolUniverse", "Medea")
    missing: list[str] = []
    for name in vendor_names:
        path = root / "third_party" / "upstream" / name
        if not path.exists() or not path.is_dir() or not any(path.rglob("*")):
            missing.append(name)
    if missing:
        raise PreflightError(
            "vendored MIMS repos are required for the production workflow: "
            + ", ".join(missing)
            + "; run `make vendor-repos` before integration testing"
        )
    return vendor_names


def validate_docker_available() -> tuple[str, ...]:
    """Validate Docker and Docker Compose CLI availability.

    Acceptance criteria:
        1. `docker` executable must be on PATH.
        2. `docker compose version` must exit successfully.
        3. Function does not start containers.

    Returns:
        Names of Docker commands checked.

    Raises:
        PreflightError: If Docker or Compose is unavailable.
    """
    if shutil.which("docker") is None:
        raise PreflightError("docker executable is required for full-stack integration")
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PreflightError(f"docker compose is unavailable: {error}") from error
    return ("docker", "docker compose")


def validate_gpu_visible(require_gpu: bool) -> tuple[str, ...]:
    """Validate GPU visibility when requested.

    Acceptance criteria:
        1. If `require_gpu` is false, no GPU probe is performed.
        2. If true, `nvidia-smi` must exist and exit successfully.
        3. Function does not mutate system state.

    Args:
        require_gpu: Whether to require a visible NVIDIA GPU.

    Returns:
        Tuple naming checked GPU prerequisites.

    Raises:
        PreflightError: If GPU is required but not visible.
    """
    if not require_gpu:
        return ()
    if shutil.which("nvidia-smi") is None:
        raise PreflightError("nvidia-smi is required when --require-gpu is set")
    try:
        subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PreflightError(f"GPU probe failed: {error}") from error
    return ("nvidia-smi",)


def run_preflight(
    *,
    requirements_path: Path,
    environment: Mapping[str, str],
    root: Path,
    require_docker: bool,
    require_gpu: bool,
) -> PreflightResult:
    """Run deterministic full-stack preflight validation.

    Acceptance criteria:
        1. Validates required environment from config.
        2. Validates report PDF path.
        3. Validates non-placeholder vLLM model id.
        4. Validates vendor repositories.
        5. Optionally validates Docker and GPU availability.
        6. Does not start services or fabricate readiness.

    Args:
        requirements_path: Full-stack requirements JSON.
        environment: Environment mapping.
        root: Repository root.
        require_docker: Whether to require Docker CLI.
        require_gpu: Whether to require visible NVIDIA GPU.

    Returns:
        Preflight validation summary.
    """
    requirements = load_requirements(requirements_path)
    checked: list[str] = []
    checked.extend(
        validate_required_environment(
            tuple(requirements.get("required_environment", [])),
            environment,
        )
    )
    checked.append(str(validate_report_path(env_value("TRANSLUME_E2E_REPORT_PATH", environment))))
    vllm = requirements.get("vllm", {})
    if not isinstance(vllm, dict):
        raise PreflightError("vllm requirements must be an object")
    checked.append(
        validate_model_identifier(
            env_value(str(vllm.get("model_env", "VLLM_MODEL")), environment),
            tuple(str(item) for item in vllm.get("model_id_disallowed_exact", [])),
        )
    )
    checked.extend(validate_vendor_repositories(root))
    if require_docker:
        checked.extend(validate_docker_available())
    checked.extend(validate_gpu_visible(require_gpu))
    return PreflightResult(checked_items=tuple(checked))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate prerequisites for Translume full-stack GPU integration."
    )
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--require-docker", action="store_true")
    parser.add_argument("--require-gpu", action="store_true")
    args = parser.parse_args()
    try:
        result = run_preflight(
            requirements_path=args.requirements,
            environment=os.environ,
            root=ROOT,
            require_docker=args.require_docker,
            require_gpu=args.require_gpu,
        )
    except (OSError, ValueError, PreflightError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        return 1
    print(
        json.dumps(
            {"status": "ok", "checked_items": list(result.checked_items)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
