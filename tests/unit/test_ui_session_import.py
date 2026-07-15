from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

import translume_ui.session_import as session_import
from translume_ui.session_import import SessionImportError, load_pathway_session_zip


PATHWAY = "# Pathway\nSaved pathway analysis.\n"
RESEARCH = "# Research\nSaved research memo.\n"
SUMMARY = "# Tumor board\nSaved causal summary.\n"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest() -> str:
    return json.dumps(
        {
            "diagnosis": "Example sarcoma",
            "pathway_analysis_sha256": _sha256(PATHWAY.strip()),
            "research_memo_sha256": _sha256(RESEARCH.strip()),
        }
    )


def _artifact_names(
    *,
    root: str = "session_example/",
    run_id: str = "run_example",
) -> dict[str, str]:
    pathway_root = f"{root}pathway_output_comprehensive/{run_id}"
    tumor_root = f"{root}tumor_board_output/{run_id}"
    return {
        "pathway": (
            f"{pathway_root}/"
            "state_after_trial_prescreens.pathway_analysis.md"
        ),
        "research": (
            f"{pathway_root}/"
            "state_after_trial_prescreens.research_memo.md"
        ),
        "summary": f"{tumor_root}/onco_board_summary.md",
        "manifest": f"{tumor_root}/onco_board_summary.manifest.json",
    }


def _write_session_zip(
    path: Path,
    *,
    root: str = "session_example/",
    run_id: str = "run_example",
    omitted: set[str] | None = None,
    manifest: str | None = None,
) -> Path:
    names = _artifact_names(root=root, run_id=run_id)
    values = {
        "pathway": PATHWAY,
        "research": RESEARCH,
        "summary": SUMMARY,
        "manifest": _manifest() if manifest is None else manifest,
    }
    skipped = set() if omitted is None else set(omitted)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for kind, name in names.items():
            if kind not in skipped:
                archive.writestr(name, values[kind])
        archive.writestr(f"{root}precision_oncology_outputs/cache.json", "{}")
    return path


def test_load_pathway_session_zip_with_session_root(tmp_path: Path) -> None:
    zip_path = _write_session_zip(tmp_path / "saved.zip")

    imported = load_pathway_session_zip(zip_path)

    assert imported.session_id == "session_example"
    assert imported.run_id == "run_example"
    assert imported.pathway_analysis_markdown == PATHWAY
    assert imported.research_memo_markdown == RESEARCH
    assert imported.tumor_board_summary_markdown == SUMMARY
    assert imported.manifest["diagnosis"] == "Example sarcoma"


def test_load_pathway_session_zip_with_rootless_contents(tmp_path: Path) -> None:
    zip_path = _write_session_zip(
        tmp_path / "session_rootless.zip",
        root="",
    )

    imported = load_pathway_session_zip(zip_path)

    assert imported.session_id == "session_rootless"
    assert imported.run_id == "run_example"


@pytest.mark.parametrize("missing", ["pathway", "research", "summary", "manifest"])
def test_load_pathway_session_zip_requires_every_artifact(
    tmp_path: Path,
    missing: str,
) -> None:
    zip_path = _write_session_zip(
        tmp_path / "incomplete.zip",
        omitted={missing},
    )

    with pytest.raises(SessionImportError, match="complete pathway run"):
        load_pathway_session_zip(zip_path)


def test_load_pathway_session_zip_rejects_multiple_runs(tmp_path: Path) -> None:
    zip_path = tmp_path / "multiple.zip"
    first = _artifact_names(run_id="run_first")
    second = _artifact_names(run_id="run_second")
    values = {
        "pathway": PATHWAY,
        "research": RESEARCH,
        "summary": SUMMARY,
        "manifest": _manifest(),
    }
    with zipfile.ZipFile(zip_path, "w") as archive:
        for names in (first, second):
            for kind, name in names.items():
                archive.writestr(name, values[kind])

    with pytest.raises(SessionImportError, match="multiple complete runs"):
        load_pathway_session_zip(zip_path)


def test_load_pathway_session_zip_rejects_hash_mismatch(tmp_path: Path) -> None:
    manifest = json.loads(_manifest())
    manifest["pathway_analysis_sha256"] = "0" * 64
    zip_path = _write_session_zip(
        tmp_path / "mismatch.zip",
        manifest=json.dumps(manifest),
    )

    with pytest.raises(SessionImportError, match="verification"):
        load_pathway_session_zip(zip_path)


def test_load_pathway_session_zip_rejects_invalid_manifest(tmp_path: Path) -> None:
    zip_path = _write_session_zip(
        tmp_path / "invalid-json.zip",
        manifest="not-json",
    )

    with pytest.raises(SessionImportError, match="not valid JSON"):
        load_pathway_session_zip(zip_path)


def test_load_pathway_session_zip_rejects_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../escaped.md", "unsafe")

    with pytest.raises(SessionImportError, match="unsafe path"):
        load_pathway_session_zip(zip_path)


def test_validate_archive_members_rejects_symbolic_links() -> None:
    member = zipfile.ZipInfo("session_example/link")
    member.external_attr = (stat.S_IFLNK | 0o777) << 16

    with pytest.raises(SessionImportError, match="must not contain links"):
        session_import.validate_archive_members([member])


def test_validate_archive_members_rejects_excessive_member_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_import, "MAX_MEMBERS", 1)
    members = [zipfile.ZipInfo("first"), zipfile.ZipInfo("second")]

    with pytest.raises(SessionImportError, match="too many files"):
        session_import.validate_archive_members(members)


def test_validate_archive_members_rejects_large_expanded_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_import, "MAX_EXPANDED_BYTES", 1)
    member = zipfile.ZipInfo("session_example/file")
    member.file_size = 2
    member.compress_size = 2

    with pytest.raises(SessionImportError, match="Expanded saved session"):
        session_import.validate_archive_members([member])


def test_validate_archive_members_rejects_unsafe_compression_ratio() -> None:
    member = zipfile.ZipInfo("session_example/file")
    member.file_size = 2_000
    member.compress_size = 1

    with pytest.raises(SessionImportError, match="unsafe compression ratio"):
        session_import.validate_archive_members([member])


def test_load_pathway_session_zip_rejects_non_zip_file(tmp_path: Path) -> None:
    path = tmp_path / "session.txt"
    path.write_text("not a zip", encoding="utf-8")

    with pytest.raises(SessionImportError, match="must be a .zip"):
        load_pathway_session_zip(path)
