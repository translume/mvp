"""Install and verify the exact vendor source snapshots shipped in this ZIP."""

from __future__ import annotations

import hashlib
import json
import posixpath
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from translume_core.vendor.repositories import VendorRepositoryError


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _entries(root: Path) -> list[dict[str, str]]:
    payload = json.loads(
        (root / "third_party/vendor_archives.lock.json").read_text("utf-8")
    )
    entries = payload.get("archives")
    if not isinstance(entries, list) or len(entries) != 3:
        raise VendorRepositoryError("Expected three locked MIMS source archives")
    expected = {"Medea", "OptimusKG", "ToolUniverse"}
    if {item.get("name") for item in entries} != expected:
        raise VendorRepositoryError("MIMS archive lock has unexpected repositories")
    return entries


def _archive_files(archive: zipfile.ZipFile, prefix: str):
    seen: set[str] = set()
    for member in archive.infolist():
        if member.is_dir():
            continue
        name = PurePosixPath(member.filename)
        if (
            not member.filename.startswith(prefix + "/")
            or name.is_absolute()
            or ".." in name.parts
            or "\\" in member.filename
        ):
            raise VendorRepositoryError("Unsafe path in vendor source archive")
        relative = PurePosixPath(*name.parts[1:])
        if not relative.parts or str(relative) in seen:
            raise VendorRepositoryError("Duplicate or empty vendor source path")
        seen.add(str(relative))
        yield member, relative


def _link_target(archive: zipfile.ZipFile, member, relative: PurePosixPath) -> str:
    """Validate a source symlink remains inside its own source snapshot."""
    target = archive.read(member).decode("utf-8")
    normalized = posixpath.normpath(str(relative.parent / target))
    if (
        not target or "\\" in target or "\x00" in target
        or PurePosixPath(target).is_absolute()
        or normalized == ".." or normalized.startswith("../")
    ):
        raise VendorRepositoryError("Unsafe symlink in vendor source archive")
    return target


def install_packaged_vendor_sources(root: Path) -> None:
    """Extract verified original archives without altering their source files.

    Acceptance criteria:
        1. Only the three SHA256-pinned bundled archives are accepted.
        2. Existing verified trees are reused; unrelated trees are not replaced.
        3. Traversal and escaping symlinks fail; in-tree links are preserved.
        4. No Git history or upstream commit identity is fabricated.
    """
    root = root.resolve()
    for item in _entries(root):
        name = item["name"]
        archive_path = root / "third_party/zips" / f"{name}.zip"
        if _sha256(archive_path) != item["sha256"]:
            raise VendorRepositoryError(f"Source archive checksum mismatch: {name}")
        destination = root / "third_party/upstream" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and any(
            p.name != ".gitkeep" for p in destination.iterdir()
        ):
            verify_packaged_vendor_source(root, item)
            continue
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            staging = Path(temporary) / name
            staging.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                for member, relative in _archive_files(archive, item["root"]):
                    output = staging / str(relative)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    if any(parent.is_symlink() for parent in output.parents):
                        raise VendorRepositoryError("Vendor member has symlink parent")
                    if stat.S_ISLNK(member.external_attr >> 16):
                        output.symlink_to(_link_target(archive, member, relative))
                        continue
                    with archive.open(member) as source, output.open("wb") as target:
                        shutil.copyfileobj(source, target)
            if destination.exists():
                marker = destination / ".gitkeep"
                if marker.is_file():
                    marker.unlink()
                destination.rmdir()
            staging.rename(destination)
        verify_packaged_vendor_source(root, item)


def verify_packaged_vendor_source(root: Path, item: dict[str, str]) -> None:
    """Verify every vendor source byte against the SHA256-pinned archive.

    Acceptance criteria:
        1. Missing, modified, additional source files and altered symlinks fail.
        2. Python bytecode caches do not count as upstream source changes.
        3. Source trees and archives are never modified during validation.
    """
    name = item["name"]
    archive_path = root / "third_party/zips" / f"{name}.zip"
    destination = root / "third_party/upstream" / name
    if not archive_path.is_file() or _sha256(archive_path) != item["sha256"]:
        raise VendorRepositoryError(f"Unverified vendor archive: {name}")
    if not destination.is_dir() or destination.is_symlink():
        raise VendorRepositoryError(f"Missing packaged vendor source: {name}")
    expected: set[str] = set()
    with zipfile.ZipFile(archive_path) as archive:
        for member, relative in _archive_files(archive, item["root"]):
            expected.add(str(relative))
            source_path = destination / str(relative)
            if stat.S_ISLNK(member.external_attr >> 16):
                target = _link_target(archive, member, relative)
                if not source_path.is_symlink() or str(source_path.readlink()) != target:
                    raise VendorRepositoryError(f"Modified vendor symlink: {relative}")
                continue
            if not source_path.is_file() or source_path.is_symlink():
                raise VendorRepositoryError(f"Missing vendor source: {name}/{relative}")
            with archive.open(member) as stream:
                original_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if _sha256(source_path) != original_hash:
                raise VendorRepositoryError(f"Modified vendor source: {name}/{relative}")
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if (path.is_file() or path.is_symlink())
        and "__pycache__" not in path.parts
    }
    if actual != expected:
        raise VendorRepositoryError(f"Additional vendor source files in {name}")


def require_packaged_vendor_sources(root: Path) -> None:
    """Fail unless all three shipped MIMS source snapshots match their locks."""
    for item in _entries(root):
        verify_packaged_vendor_source(root, item)
