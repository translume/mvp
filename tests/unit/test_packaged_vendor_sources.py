from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest
from translume_core.vendor.packaged import (
    install_packaged_vendor_sources,
    require_packaged_vendor_sources,
)
from translume_core.vendor.repositories import VendorRepositoryError

_SOURCE_BYTES = b"# Pinned source bytes\r\nVALUE = '\xc3\xa9vidence'\n"
_VENDORS = ("Medea", "OptimusKG", "ToolUniverse")


def _source_archives(
    root: Path, *, medea_members: list[tuple[str, bytes, bool]] | None = None
) -> None:
    archive_dir = root / "third_party" / "zips"
    archive_dir.mkdir(parents=True)
    entries = []
    for name in _VENDORS:
        archive_path = archive_dir / f"{name}.zip"
        prefix = f"{name}-main"
        members = (
            medea_members
            if name == "Medea" and medea_members is not None
            else [(f"{prefix}/logic.py", _SOURCE_BYTES, False)]
        )
        with zipfile.ZipFile(archive_path, "w") as archive:
            for member_name, payload, is_link in members:
                member = zipfile.ZipInfo(member_name)
                member.create_system = 3
                member.external_attr = (
                    (stat.S_IFLNK | 0o777) if is_link else (stat.S_IFREG | 0o644)
                ) << 16
                archive.writestr(member, payload)
        entries.append(
            {
                "name": name,
                "root": prefix,
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            }
        )
    (root / "third_party/vendor_archives.lock.json").write_text(
        json.dumps({"format": 1, "archives": entries}), encoding="utf-8"
    )


def test_installer_preserves_original_bytes_is_repeatable_and_does_not_invent_git(
    tmp_path,
):
    _source_archives(tmp_path)
    marker = tmp_path / "third_party/upstream/Medea/.gitkeep"
    marker.parent.mkdir(parents=True)
    marker.touch()
    install_packaged_vendor_sources(tmp_path)
    paths = [tmp_path / "third_party/upstream" / name / "logic.py" for name in _VENDORS]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    install_packaged_vendor_sources(tmp_path)
    require_packaged_vendor_sources(tmp_path)
    assert before == [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    assert all(path.read_bytes() == _SOURCE_BYTES for path in paths)
    assert not marker.exists()
    assert not any((path.parent / ".git").exists() for path in paths)


def test_archive_checksum_tampering_fails_before_installing_any_source(tmp_path):
    _source_archives(tmp_path)
    archive = tmp_path / "third_party/zips/Medea.zip"
    with archive.open("ab") as stream:
        stream.write(b"tampered bytes after zip directory")
    with pytest.raises(VendorRepositoryError, match="checksum mismatch"):
        install_packaged_vendor_sources(tmp_path)
    assert not (tmp_path / "third_party/upstream/Medea/logic.py").exists()


@pytest.mark.parametrize(
    "member_name",
    [
        "Medea-main/../escaped.py",
        "/Medea-main/escaped.py",
        "Medea-main/dir\\escaped.py",
        "Other-main/escaped.py",
    ],
)
def test_archive_path_traversal_is_rejected_even_when_archive_is_locked(
    tmp_path, member_name
):
    _source_archives(tmp_path, medea_members=[(member_name, _SOURCE_BYTES, False)])
    with pytest.raises(VendorRepositoryError, match="Unsafe path"):
        install_packaged_vendor_sources(tmp_path)
    assert not (tmp_path / "escaped.py").exists()
    assert not (tmp_path / "third_party/upstream/escaped.py").exists()


@pytest.mark.parametrize(
    "target", [b"../outside.py", b"/tmp/outside.py", b"..\\outside.py"]
)
def test_escaping_source_symlinks_are_rejected(tmp_path, target):
    _source_archives(tmp_path, medea_members=[("Medea-main/link.py", target, True)])
    with pytest.raises(VendorRepositoryError, match="Unsafe symlink"):
        install_packaged_vendor_sources(tmp_path)


def test_in_tree_symlink_is_preserved_and_its_target_cannot_be_replaced(tmp_path):
    _source_archives(
        tmp_path,
        medea_members=[
            ("Medea-main/logic.py", _SOURCE_BYTES, False),
            ("Medea-main/link.py", b"logic.py", True),
        ],
    )
    install_packaged_vendor_sources(tmp_path)
    link = tmp_path / "third_party/upstream/Medea/link.py"
    assert link.is_symlink()
    assert link.read_bytes() == _SOURCE_BYTES
    assert str(link.readlink()) == "logic.py"
    require_packaged_vendor_sources(tmp_path)
    link.unlink()
    link.symlink_to("../outside.py")
    with pytest.raises(VendorRepositoryError, match="Modified vendor symlink"):
        require_packaged_vendor_sources(tmp_path)


def test_archive_member_cannot_write_through_a_preceding_directory_symlink(tmp_path):
    _source_archives(
        tmp_path,
        medea_members=[
            ("Medea-main/directory", b".", True),
            ("Medea-main/directory/logic.py", _SOURCE_BYTES, False),
        ],
    )
    with pytest.raises(VendorRepositoryError, match="symlink parent"):
        install_packaged_vendor_sources(tmp_path)


def test_modified_existing_tree_is_rejected_without_overwriting_user_changes(tmp_path):
    _source_archives(tmp_path)
    install_packaged_vendor_sources(tmp_path)
    source = tmp_path / "third_party/upstream/Medea/logic.py"
    source.write_bytes(b"changed source")
    with pytest.raises(VendorRepositoryError, match="Modified vendor source"):
        install_packaged_vendor_sources(tmp_path)
    assert source.read_bytes() == b"changed source"


def test_extra_source_is_rejected_but_compiled_python_cache_is_ignored(tmp_path):
    _source_archives(tmp_path)
    install_packaged_vendor_sources(tmp_path)
    vendor = tmp_path / "third_party/upstream/OptimusKG"
    cache = vendor / "__pycache__"
    cache.mkdir()
    (cache / "logic.cpython-312.pyc").write_bytes(b"compiled cache")
    require_packaged_vendor_sources(tmp_path)
    (vendor / "unexpected.py").write_text("unexpected source", encoding="utf-8")
    with pytest.raises(VendorRepositoryError, match="Additional vendor source"):
        require_packaged_vendor_sources(tmp_path)
