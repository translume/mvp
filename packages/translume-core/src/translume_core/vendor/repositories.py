from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class VendorRepositoryError(RuntimeError):
    """Raised when vendor repository state violates production requirements."""


@dataclass(frozen=True)
class VendorRepoSpec:
    """Represent one required upstream repository.

    Attributes:
        name: Repository display name.
        url: Git remote URL.
        target: Local checkout path.
    """

    name: str
    url: str
    target: Path


@dataclass(frozen=True)
class VendorRepoState:
    """Represent observed local state for one vendor repository.

    Attributes:
        name: Repository display name.
        url: Expected Git remote URL.
        target: Local checkout path.
        exists: Whether the target path exists.
        is_git_repository: Whether the target contains `.git`.
        actual_remote_url: Observed `origin` remote URL if available.
        commit: Current commit hash if available.
        branch: Current branch name if available.
        dirty: Whether tracked/untracked changes are present.
        updateable: Whether `git pull --ff-only` is expected to work.
        problems: Human-readable configuration problems.
    """

    name: str
    url: str
    target: Path
    exists: bool
    is_git_repository: bool
    actual_remote_url: str | None
    commit: str | None
    branch: str | None
    dirty: bool
    updateable: bool
    problems: tuple[str, ...]


@dataclass(frozen=True)
class VendorStatusReport:
    """Represent status for all required vendor repositories.

    Attributes:
        ok: Whether every vendor repo is a clean, updateable Git checkout.
        states: Per-repository states.
    """

    ok: bool
    states: tuple[VendorRepoState, ...]


def load_vendor_repo_specs(path: Path, root: Path) -> tuple[VendorRepoSpec, ...]:
    """Load vendor repository specs from JSON.

    Acceptance criteria:
        1. Determinism: Same JSON content and root return same specs.
        2. Validation: Missing config raises `FileNotFoundError`.
        3. Validation: Missing repository fields raise `VendorRepositoryError`.
        4. Safety: Target paths are resolved under `root`.

    Args:
        path: Vendor configuration path.
        root: Project root used to resolve target paths.

    Returns:
        Tuple of vendor repository specifications.

    Raises:
        FileNotFoundError: If `path` is missing.
        VendorRepositoryError: If config is malformed or target escapes root.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    repos = payload.get("repositories")
    if not isinstance(repos, list):
        raise VendorRepositoryError("vendor config missing repositories list")
    specs: list[VendorRepoSpec] = []
    for item in repos:
        if not isinstance(item, dict):
            raise VendorRepositoryError("each vendor repository entry must be an object")
        try:
            name = str(item["name"])
            url = str(item["url"])
            target_value = str(item["target"])
        except KeyError as error:
            raise VendorRepositoryError(
                f"vendor repository entry missing field: {error.args[0]}"
            ) from error
        target = (root / target_value).resolve()
        root_resolved = root.resolve()
        if root_resolved not in target.parents and target != root_resolved:
            raise VendorRepositoryError(f"vendor target escapes project root: {target}")
        specs.append(VendorRepoSpec(name=name, url=url, target=target))
    return tuple(specs)


def clone_or_pull_vendor_repo(spec: VendorRepoSpec) -> VendorRepoState:
    """Clone or fast-forward pull one vendor repository.

    Acceptance criteria:
        1. Missing targets are cloned from the configured URL.
        2. Existing Git checkouts are updated with `git pull --ff-only`.
        3. Non-Git existing targets raise `VendorRepositoryError`.
        4. No zip extraction or fallback bootstrap is performed here.

    Args:
        spec: Vendor repository specification.

    Returns:
        Observed repository state after clone or pull.

    Raises:
        VendorRepositoryError: If target exists but is not a Git repository, or
            if Git commands fail.
    """
    spec.target.parent.mkdir(parents=True, exist_ok=True)
    if spec.target.exists() and not is_git_repository(spec.target):
        raise VendorRepositoryError(
            "vendor target exists but is not a Git repository: "
            f"{spec.target}. Remove it or run the explicit offline bootstrap "
            "command; production vendor update requires a real `.git` checkout."
        )
    try:
        if is_git_repository(spec.target):
            run_git_command(spec.target, ("pull", "--ff-only"))
        else:
            run_command(("git", "clone", spec.url, str(spec.target)))
    except subprocess.CalledProcessError as error:
        raise VendorRepositoryError(
            f"failed to clone or pull vendor repository {spec.name}: {error}"
        ) from error
    return inspect_vendor_repo(spec)


def bootstrap_vendor_repo_from_zip(
    spec: VendorRepoSpec,
    zip_path: Path,
    *,
    force: bool,
) -> VendorRepoState:
    """Install a vendor repo from a zip for offline inspection only.

    Acceptance criteria:
        1. Missing zip raises `FileNotFoundError`.
        2. Existing targets are not replaced unless `force` is true.
        3. Result is intentionally non-updateable and fails vendor status.
        4. Archive content is copied without modifying upstream source files.

    Args:
        spec: Vendor repository specification.
        zip_path: Zip archive path.
        force: Whether to replace an existing target directory.

    Returns:
        Observed non-Git vendor repository state.

    Raises:
        FileNotFoundError: If `zip_path` is missing.
        VendorRepositoryError: If target exists and `force` is false.
    """
    if not zip_path.exists():
        raise FileNotFoundError(str(zip_path))
    if spec.target.exists():
        if not force:
            raise VendorRepositoryError(
                f"target already exists: {spec.target}; rerun with --force to replace"
            )
        shutil.rmtree(spec.target)
    spec.target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        common_root = common_archive_root(names)
        for name in names:
            output_name = name[len(common_root) :].lstrip("/") if common_root else name
            if not output_name:
                continue
            destination = spec.target / output_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
    return inspect_vendor_repo(spec)


def common_archive_root(names: Sequence[str]) -> str:
    """Return the single top-level archive directory if one exists.

    Acceptance criteria:
        1. Determinism: Same names return the same root.
        2. Empty inputs return an empty string.
        3. Multiple roots return an empty string.
        4. No mutation: Input sequence is not modified.

    Args:
        names: Archive member names.

    Returns:
        Common root directory or an empty string.
    """
    roots = {name.split("/", 1)[0] for name in names if "/" in name}
    return next(iter(roots)) if len(roots) == 1 else ""


def inspect_vendor_repo(spec: VendorRepoSpec) -> VendorRepoState:
    """Inspect one vendor repository without mutating it.

    Acceptance criteria:
        1. Missing targets are reported as non-updateable.
        2. Non-Git targets are reported as non-updateable.
        3. Git metadata is read only through `git` commands.
        4. Problems explain exactly why vendor status fails.

    Args:
        spec: Vendor repository specification.

    Returns:
        Observed vendor repository state.
    """
    exists = spec.target.exists()
    is_git = is_git_repository(spec.target)
    problems: list[str] = []
    remote = None
    commit = None
    branch = None
    dirty = False
    if not exists:
        problems.append("missing target directory")
    elif not is_git:
        problems.append("target exists but is not a Git repository")
    else:
        remote = maybe_git_output(spec.target, ("config", "--get", "remote.origin.url"))
        commit = maybe_git_output(spec.target, ("rev-parse", "HEAD"))
        branch = maybe_git_output(spec.target, ("rev-parse", "--abbrev-ref", "HEAD"))
        dirty_output = maybe_git_output(spec.target, ("status", "--porcelain"))
        dirty = bool(dirty_output)
        if remote is None:
            problems.append("missing origin remote")
        elif normalize_git_url(remote) != normalize_git_url(spec.url):
            problems.append(f"origin remote mismatch: {remote}")
        if commit is None:
            problems.append("cannot resolve current commit")
        if branch is None:
            problems.append("cannot resolve current branch")
        if dirty:
            problems.append("working tree has uncommitted or untracked changes")
    return VendorRepoState(
        name=spec.name,
        url=spec.url,
        target=spec.target,
        exists=exists,
        is_git_repository=is_git,
        actual_remote_url=remote,
        commit=commit,
        branch=branch,
        dirty=dirty,
        updateable=not problems,
        problems=tuple(problems),
    )


def inspect_vendor_repos(specs: Sequence[VendorRepoSpec]) -> VendorStatusReport:
    """Inspect all required vendor repositories.

    Acceptance criteria:
        1. Determinism: Same repository state returns same status.
        2. No mutation: Repositories are not modified.
        3. Completeness: Every spec has one state entry.
        4. Status: Report is OK only when every repo is updateable.

    Args:
        specs: Vendor repository specifications.

    Returns:
        Vendor status report.
    """
    states = tuple(inspect_vendor_repo(spec) for spec in specs)
    return VendorStatusReport(ok=all(state.updateable for state in states), states=states)


def require_updateable_vendor_repos(specs: Sequence[VendorRepoSpec]) -> VendorStatusReport:
    """Return status or raise if any vendor repository is not updateable.

    Acceptance criteria:
        1. Fails when any vendor repo is missing.
        2. Fails when any vendor repo lacks `.git`.
        3. Fails when any vendor repo has wrong remote or dirty state.
        4. Error message lists every failing repo and problem.

    Args:
        specs: Vendor repository specifications.

    Returns:
        OK vendor status report.

    Raises:
        VendorRepositoryError: If any repository is not updateable.
    """
    report = inspect_vendor_repos(specs)
    if report.ok:
        return report
    raise VendorRepositoryError(render_vendor_status(report))


def render_vendor_status(report: VendorStatusReport) -> str:
    """Render human-readable vendor repository status.

    Acceptance criteria:
        1. Includes every repository name.
        2. Includes target path and updateability.
        3. Includes problems for failing repositories.
        4. Output is deterministic.

    Args:
        report: Vendor status report.

    Returns:
        Human-readable status string.
    """
    lines = ["Vendor repository status:"]
    for state in report.states:
        marker = "OK" if state.updateable else "FAIL"
        lines.append(f"- {state.name}: {marker}")
        lines.append(f"  target: {state.target}")
        lines.append(f"  expected_remote: {state.url}")
        lines.append(f"  actual_remote: {state.actual_remote_url or '<missing>'}")
        lines.append(f"  branch: {state.branch or '<missing>'}")
        lines.append(f"  commit: {state.commit or '<missing>'}")
        if state.problems:
            for problem in state.problems:
                lines.append(f"  problem: {problem}")
    return "\n".join(lines)


def vendor_status_to_dict(report: VendorStatusReport) -> dict[str, object]:
    """Return JSON-serializable vendor status.

    Acceptance criteria:
        1. Output contains top-level `ok` flag.
        2. Paths are converted to strings.
        3. Every state is included.
        4. Output contains no runtime-only objects.

    Args:
        report: Vendor status report.

    Returns:
        JSON-serializable mapping.
    """
    return {
        "ok": report.ok,
        "repositories": [
            {**asdict(state), "target": str(state.target)}
            for state in report.states
        ],
    }


def manifest_record(state: VendorRepoState) -> dict[str, object]:
    """Return a lock-manifest record for one git vendor checkout.

    Acceptance criteria:
        1. Non-updateable states raise `VendorRepositoryError`.
        2. Record includes repo name, URL, branch, commit, and target.
        3. Record marks update_mode as `git`.
        4. Record is JSON-serializable.

    Args:
        state: Observed vendor repository state.

    Returns:
        Manifest mapping.

    Raises:
        VendorRepositoryError: If `state` is not updateable.
    """
    if not state.updateable:
        raise VendorRepositoryError(
            f"cannot write git manifest for non-updateable repo: {state.name}"
        )
    return {
        "name": state.name,
        "url": state.url,
        "target": str(state.target),
        "remote_url": state.actual_remote_url,
        "branch": state.branch,
        "commit": state.commit,
        "update_mode": "git",
        "updateable": True,
    }


def zip_bootstrap_manifest_record(
    spec: VendorRepoSpec,
    zip_path: Path,
    state: VendorRepoState,
) -> dict[str, object]:
    """Return manifest record for an offline zip bootstrap.

    Acceptance criteria:
        1. Record clearly marks update_mode as `zip_bootstrap`.
        2. Record clearly marks updateable as false.
        3. Record includes source zip path.
        4. Record is JSON-serializable.

    Args:
        spec: Vendor repo specification.
        zip_path: Source zip archive path.
        state: Observed post-bootstrap repo state.

    Returns:
        Manifest mapping.
    """
    return {
        "name": spec.name,
        "url": spec.url,
        "target": str(spec.target),
        "source_zip": str(zip_path),
        "update_mode": "zip_bootstrap",
        "updateable": False,
        "status_note": (
            "Offline zip bootstrap is not production-updateable. "
            "Run `make vendor-repos` on a networked VM to create real Git clones."
        ),
        "problems": list(state.problems),
    }


def write_manifest(manifest_dir: Path, record: Mapping[str, object]) -> Path:
    """Write one vendor manifest record.

    Acceptance criteria:
        1. Manifest directory is created if needed.
        2. File name is based on repository name.
        3. JSON is written with deterministic key order.
        4. Returns created path.

    Args:
        manifest_dir: Directory for manifest files.
        record: JSON-serializable manifest record.

    Returns:
        Written manifest path.
    """
    manifest_dir.mkdir(parents=True, exist_ok=True)
    name = str(record["name"]).casefold()
    path = manifest_dir / f"{name}.lock.json"
    path.write_text(json.dumps(dict(record), indent=2, sort_keys=True), encoding="utf-8")
    return path


def is_git_repository(path: Path) -> bool:
    """Return whether `path` is a Git worktree.

    Acceptance criteria:
        1. Missing paths return false.
        2. Non-directories return false.
        3. `.git` directory or file marks a worktree.
        4. Function is pure except filesystem inspection.

    Args:
        path: Candidate repository path.

    Returns:
        True if path contains `.git`.
    """
    git_path = path / ".git"
    return path.is_dir() and git_path.exists()


def normalize_git_url(url: str) -> str:
    """Normalize Git remote URLs for equality checks.

    Acceptance criteria:
        1. Trailing `.git` is ignored.
        2. Trailing slashes are ignored.
        3. SSH GitHub form is normalized to HTTPS-like host/path.
        4. Comparison is case-insensitive.

    Args:
        url: Raw remote URL.

    Returns:
        Normalized URL string.
    """
    value = url.strip().casefold().rstrip("/")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def run_git_command(repo_path: Path, args: Sequence[str]) -> str:
    """Run a Git command in an existing repository.

    Acceptance criteria:
        1. Command is executed through the `git` binary.
        2. Non-zero exit raises `CalledProcessError`.
        3. Captured stdout is returned stripped.
        4. Side effect is isolated to this boundary function.

    Args:
        repo_path: Git repository path.
        args: Git command arguments excluding `git -C repo_path`.

    Returns:
        Stripped standard output.
    """
    return subprocess.check_output(
        ["git", "-C", str(repo_path), *args],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def maybe_git_output(repo_path: Path, args: Sequence[str]) -> str | None:
    try:
        return run_git_command(repo_path, args)
    except (OSError, subprocess.CalledProcessError):
        return None


def run_command(argv: Sequence[str]) -> None:
    """Run one subprocess command.

    Acceptance criteria:
        1. Non-zero exit raises `CalledProcessError`.
        2. Command arguments are passed without shell interpolation.
        3. Side effects are isolated to this boundary function.
        4. Captured output is not fabricated.

    Args:
        argv: Command vector.
    """
    subprocess.run(list(argv), check=True)
