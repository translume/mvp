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

from translume_core.indexing.retrieval_scope import require_lexical_retrieval_scope
from translume_core.prime_directives import (
    PrimeDirectiveViolation,
    assert_prime_directives,
)
from translume_core.vendor.repositories import (
    VendorRepositoryError,
    load_vendor_repo_specs,
    require_updateable_vendor_repos,
)

try:
    from scripts.download_mims_data import (
        MimsDataError,
        inspect_medeadb,
        inspect_optimuskg_cache,
        validate_optimuskg_parquet,
    )
except ModuleNotFoundError:  # direct execution from the scripts directory
    from download_mims_data import (  # type: ignore[no-redef]
        MimsDataError,
        inspect_medeadb,
        inspect_optimuskg_cache,
        validate_optimuskg_parquet,
    )


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
    """Validate that MIMS vendors are real updateable Git clones.

    Acceptance criteria:
        1. OptimusKG, ToolUniverse, and Medea must be configured.
        2. Each target must contain a `.git` worktree.
        3. Each target must match the configured origin remote.
        4. Zip-extracted vendor directories fail preflight.
        5. Function does not import or mutate vendor repositories.

    Args:
        root: Repository root.

    Returns:
        Tuple of validated vendor repository names.

    Raises:
        PreflightError: If any vendor repository is not updateable.
    """
    config = root / "third_party" / "vendor_repos.json"
    try:
        specs = load_vendor_repo_specs(config, root)
        report = require_updateable_vendor_repos(specs)
    except (FileNotFoundError, VendorRepositoryError) as error:
        raise PreflightError(
            "Harvard MIMS vendors must be real Git clones for production. "
            "Run `make vendor-repos` on a networked VM and rerun preflight. "
            f"Details: {error}"
        ) from error
    return tuple(state.name for state in report.states)


def _host_path(value: str, root: Path) -> Path:
    """Resolve a host path relative to the repository root when necessary."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def validate_mims_data(
    root: Path,
    environment: Mapping[str, str],
) -> tuple[str, ...]:
    """Validate host-side MedeaDB and OptimusKG caches before Docker starts.

    Acceptance criteria:
        1. MedeaDB contains all resource families consumed by upstream Medea.
        2. OptimusKG contains the exact LCC or full parquet pair configured.
        3. Uses host paths, not container-only `/app` paths.
        4. Does not download or mutate data during preflight.
    """
    medea_host = env_value("MEDEA_DATA_HOST_DIR", environment)
    explicit_medeadb = env_value("MEDEADB_PATH", environment)
    if explicit_medeadb and not explicit_medeadb.startswith("/app/"):
        medeadb_path = _host_path(explicit_medeadb, root)
    elif medea_host:
        medeadb_path = _host_path(medea_host, root) / "MedeaDB"
    else:
        medeadb_path = root / "data" / "medea_cache" / "MedeaDB"

    optimus_host = env_value("OPTIMUSKG_DATA_HOST_DIR", environment)
    explicit_cache = env_value("OPTIMUSKG_CACHE_DIR", environment)
    if explicit_cache and not explicit_cache.startswith("/app/"):
        optimus_cache = _host_path(explicit_cache, root)
    elif optimus_host:
        optimus_cache = _host_path(optimus_host, root)
    else:
        optimus_cache = root / "data" / "optimuskg_cache"
    use_lcc = env_value("OPTIMUSKG_USE_LCC", environment).casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }

    medea = inspect_medeadb(medeadb_path)
    if not medea.available:
        raise PreflightError(
            "MedeaDB is incomplete at "
            f"{medea.path}: {', '.join(medea.missing)}. "
            "Run `make medea-data`."
        )
    optimus = inspect_optimuskg_cache(optimus_cache, use_lcc=use_lcc)
    if not optimus.available:
        raise PreflightError(
            "OptimusKG cache is incomplete at "
            f"{optimus.cache_dir}: {', '.join(optimus.missing)}. "
            "Run `make optimuskg-data`."
        )
    try:
        validate_optimuskg_parquet(
            Path(str(optimus.nodes_path)),
            Path(str(optimus.edges_path)),
        )
    except MimsDataError as error:
        raise PreflightError(
            "OptimusKG cache exists but cannot be parsed by Translume: "
            f"{error}. Run `make optimuskg-data`."
        ) from error
    return (
        f"medeadb:{medea.path}",
        f"optimuskg_cache:{optimus.cache_dir}",
    )


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


def validate_retrieval_scope(
    requirements: Mapping[str, Any], environment: Mapping[str, str]
) -> str:
    """Validate full-stack retrieval scope is lexical-only for this MVP.

    Acceptance criteria:
        1. Reads retrieval scope from the requirements config.
        2. Accepts lexical mode.
        3. Rejects vector/HNSW/hybrid modes until embeddings are real.
        4. Returns the checked mode for diagnostics.
    """
    config = requirements.get("retrieval_scope", {})
    if not isinstance(config, dict):
        raise PreflightError("retrieval_scope requirements must be an object")
    env_name = str(config.get("mode_env", "TRANSLUME_RETRIEVAL_MODE"))
    mode = env_value(env_name, environment) or str(
        config.get("required_mode", "lexical")
    )
    try:
        scope = require_lexical_retrieval_scope(mode)
    except Exception as error:
        raise PreflightError(str(error)) from error
    return f"retrieval_mode:{scope.mode}"


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
        5. Validates host-side MedeaDB and OptimusKG data caches.
        6. Optionally validates Docker and GPU availability.
        7. Validates retrieval scope does not overclaim vector/HNSW.
        8. Does not start services or fabricate readiness.

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
    try:
        assert_prime_directives(environment=environment, root=root, force=True)
    except PrimeDirectiveViolation as error:
        raise PreflightError(str(error)) from error
    checked.append("prime_directives_gate")
    checked.extend(
        validate_required_environment(
            tuple(requirements.get("required_environment", [])),
            environment,
        )
    )
    checked.append(
        str(validate_report_path(env_value("TRANSLUME_E2E_REPORT_PATH", environment)))
    )
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
    checked.extend(validate_mims_data(root, environment))
    checked.append(validate_retrieval_scope(requirements, environment))
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
