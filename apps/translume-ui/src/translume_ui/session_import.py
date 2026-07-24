"""Safely load pathway-display artifacts from a completed session ZIP."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Final, Mapping

from pydantic import ValidationError

from translume_schemas.export import ReviewPacketExport


MAX_ARCHIVE_BYTES: Final = 256 * 1024 * 1024
MAX_EXPANDED_BYTES: Final = 512 * 1024 * 1024
MAX_MEMBER_BYTES: Final = 8 * 1024 * 1024
MAX_MEMBERS: Final = 5_000
MAX_COMPRESSION_RATIO: Final = 1_000

_PATHWAY_FILENAME: Final = "state_after_trial_prescreens.pathway_analysis.md"
_RESEARCH_FILENAME: Final = "state_after_trial_prescreens.research_memo.md"
_SUMMARY_FILENAME: Final = "onco_board_summary.md"
_MANIFEST_FILENAME: Final = "onco_board_summary.manifest.json"
_REVIEW_PACKET_FILENAME: Final = "translume_review_packet.json"


class SessionImportError(ValueError):
    """Raised when a saved session archive cannot be loaded safely."""


@dataclass(frozen=True)
class ImportedPathwaySession:
    """Represent pathway artifacts loaded from one completed session.

    Acceptance criteria:
        1. Contains one coherent session and run identifier.
        2. Contains non-empty pathway, research, and tumor-board Markdown.
        3. Contains one schema-valid, session-coherent review packet.
        4. Exposes validated manifest metadata without filesystem extraction.
    """

    session_id: str
    run_id: str
    pathway_analysis_markdown: str
    research_memo_markdown: str
    tumor_board_summary_markdown: str
    manifest: Mapping[str, Any]
    review_packet: ReviewPacketExport


@dataclass(frozen=True)
class _ArtifactMembers:
    """Identify required pathway and review-packet archive members."""

    session_id: str
    run_id: str
    pathway: str
    research: str
    summary: str
    manifest: str
    review_packet: str


def load_pathway_session_zip(zip_path: Path) -> ImportedPathwaySession:
    """Load one coherent pathway artifact set from a ZIP archive.

    Acceptance criteria:
        1. Validation: Accept only a readable ZIP within configured limits.
        2. Safety: Reject traversal, absolute paths, links, and archive bombs.
        3. Coherence: Require exactly one complete shared ``run_*`` artifact set.
        4. Integrity: Validate available manifest SHA-256 values.
        5. Isolation: Read required members directly without extracting the ZIP.

    Args:
        zip_path: Uploaded session archive.

    Returns:
        Validated pathway-display artifacts.

    Raises:
        SessionImportError: If the archive or required artifacts are invalid.
    """
    if not zip_path.is_file():
        raise SessionImportError("Upload a saved session ZIP before loading.")
    if zip_path.suffix.casefold() != ".zip":
        raise SessionImportError("Saved session upload must be a .zip file.")
    if zip_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SessionImportError("Saved session ZIP exceeds the 256 MiB limit.")

    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = validate_archive_members(archive.infolist())
            selected = select_pathway_artifact_members(members, zip_path.stem)
            pathway = _read_required_markdown(archive, selected.pathway)
            research = _read_required_markdown(archive, selected.research)
            summary = _read_required_markdown(archive, selected.summary)
            manifest = _read_manifest(archive, selected.manifest)
            review_packet = _read_review_packet(
                archive,
                selected.review_packet,
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise SessionImportError("Saved session upload is not a readable ZIP.") from error

    validate_tumor_board_manifest(manifest, pathway, research)
    session_id = _validated_review_packet_session(
        review_packet,
        selected.session_id,
    )
    return ImportedPathwaySession(
        session_id=session_id,
        run_id=selected.run_id,
        pathway_analysis_markdown=pathway,
        research_memo_markdown=research,
        tumor_board_summary_markdown=summary,
        manifest=MappingProxyType(dict(manifest)),
        review_packet=review_packet,
    )


def validate_archive_members(
    members: list[zipfile.ZipInfo],
) -> tuple[zipfile.ZipInfo, ...]:
    """Return validated archive members without mutating the input list.

    Acceptance criteria:
        1. Rejects unsafe paths and symbolic links.
        2. Enforces member-count, expanded-size, member-size, and ratio limits.
        3. Returns an immutable sequence in archive order.
    """
    if len(members) > MAX_MEMBERS:
        raise SessionImportError("Saved session ZIP contains too many files.")
    total_size = 0
    for member in members:
        _validate_member_path(member.filename)
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise SessionImportError("Saved session ZIP must not contain links.")
        total_size += member.file_size
        if member.file_size > MAX_MEMBER_BYTES:
            raise SessionImportError(
                f"Archive member is too large: {member.filename}"
            )
        if member.file_size and not member.compress_size:
            raise SessionImportError(
                f"Archive member has an unsafe compression ratio: {member.filename}"
            )
        if (
            member.compress_size
            and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise SessionImportError(
                f"Archive member has an unsafe compression ratio: {member.filename}"
            )
    if total_size > MAX_EXPANDED_BYTES:
        raise SessionImportError("Expanded saved session exceeds the 512 MiB limit.")
    return tuple(members)


def select_pathway_artifact_members(
    members: tuple[zipfile.ZipInfo, ...],
    archive_stem: str,
) -> _ArtifactMembers:
    """Select exactly one complete, coherent run from validated members.

    Acceptance criteria:
        1. Supports an optional top-level ``session_*`` directory.
        2. Requires all four display and validation artifacts for one run.
        3. Rejects missing, duplicate, mismatched, or ambiguous run sets.
        4. Performs no I/O and does not mutate inputs.
    """
    artifacts_by_run: dict[str, dict[str, str]] = {}
    sessions_by_run: dict[str, set[str]] = {}
    review_packets: list[tuple[str, str]] = []
    for member in members:
        if member.is_dir():
            continue
        packet_session = _locate_review_packet(member.filename)
        if packet_session is not None:
            review_packets.append((member.filename, packet_session))
            continue
        located = _locate_artifact(member.filename)
        if located is None:
            continue
        run_id, session_id, kind = located
        run_artifacts = artifacts_by_run.setdefault(run_id, {})
        if kind in run_artifacts:
            raise SessionImportError(
                f"Saved session ZIP contains duplicate {kind} files for {run_id}."
            )
        run_artifacts[kind] = member.filename
        if session_id:
            sessions_by_run.setdefault(run_id, set()).add(session_id)

    required = {"pathway", "research", "summary", "manifest"}
    complete_runs = [
        run_id
        for run_id, artifacts in artifacts_by_run.items()
        if set(artifacts) == required
    ]
    if not complete_runs:
        found = sorted({kind for artifacts in artifacts_by_run.values() for kind in artifacts})
        missing = ", ".join(sorted(required - set(found)))
        detail = f" Missing: {missing}." if missing else ""
        raise SessionImportError(
            "Saved session ZIP does not contain one complete pathway run." + detail
        )
    if len(complete_runs) != 1:
        raise SessionImportError(
            "Saved session ZIP contains multiple complete runs; upload one run only."
        )
    run_id = complete_runs[0]
    sessions = sessions_by_run.get(run_id, set())
    if len(sessions) > 1:
        raise SessionImportError("Saved session ZIP mixes multiple session folders.")
    session_id = next(iter(sessions), _session_id_from_archive_stem(archive_stem))
    if len(review_packets) != 1:
        raise SessionImportError(
            "Saved session ZIP must contain exactly one "
            f"{_REVIEW_PACKET_FILENAME}."
        )
    review_packet, review_packet_session = review_packets[0]
    if review_packet_session and review_packet_session != session_id:
        raise SessionImportError(
            "Saved review packet is stored under a different session folder."
        )
    artifacts = artifacts_by_run[run_id]
    return _ArtifactMembers(
        session_id=session_id,
        run_id=run_id,
        pathway=artifacts["pathway"],
        research=artifacts["research"],
        summary=artifacts["summary"],
        manifest=artifacts["manifest"],
        review_packet=review_packet,
    )


def validate_tumor_board_manifest(
    manifest: Mapping[str, Any],
    pathway_markdown: str,
    research_markdown: str,
) -> None:
    """Require valid manifest metadata and verify available source hashes.

    Acceptance criteria:
        1. Requires a non-empty diagnosis.
        2. Verifies pathway and research SHA-256 values when declared.
        3. Raises a precise error for malformed hashes.
        4. Does not mutate inputs or perform I/O.
    """
    diagnosis = manifest.get("diagnosis")
    if not isinstance(diagnosis, str) or not diagnosis.strip():
        raise SessionImportError("Tumor-board manifest has no diagnosis.")
    _verify_manifest_hash(
        manifest,
        "pathway_analysis_sha256",
        pathway_markdown,
    )
    _verify_manifest_hash(
        manifest,
        "research_memo_sha256",
        research_markdown,
    )


def _locate_artifact(filename: str) -> tuple[str, str, str] | None:
    path = PurePosixPath(filename)
    parts = path.parts
    session_id = parts[0] if parts and parts[0].startswith("session_") else ""
    patterns = (
        ("pathway_output_comprehensive", _PATHWAY_FILENAME, "pathway"),
        ("pathway_output_comprehensive", _RESEARCH_FILENAME, "research"),
        ("tumor_board_output", _SUMMARY_FILENAME, "summary"),
        ("tumor_board_output", _MANIFEST_FILENAME, "manifest"),
    )
    for directory, expected_name, kind in patterns:
        if path.name != expected_name or directory not in parts:
            continue
        index = parts.index(directory)
        if index + 1 >= len(parts):
            return None
        run_id = parts[index + 1]
        if not run_id.startswith("run_"):
            return None
        return run_id, session_id, kind
    return None


def _locate_review_packet(filename: str) -> str | None:
    """Return the optional session folder for one review-packet member."""
    path = PurePosixPath(filename)
    if path.name != _REVIEW_PACKET_FILENAME:
        return None
    if len(path.parts) == 1:
        return ""
    if len(path.parts) == 2 and path.parts[0].startswith("session_"):
        return path.parts[0]
    raise SessionImportError(
        "Saved review packet must be at the archive root or session root."
    )


def _validate_member_path(filename: str) -> None:
    if "\\" in filename:
        raise SessionImportError(f"Archive member uses an unsafe path: {filename}")
    path = PurePosixPath(filename)
    if path.is_absolute() or ".." in path.parts:
        raise SessionImportError(f"Archive member uses an unsafe path: {filename}")


def _read_required_markdown(archive: zipfile.ZipFile, member_name: str) -> str:
    try:
        content = archive.read(member_name).decode("utf-8")
    except UnicodeDecodeError as error:
        raise SessionImportError(
            f"Saved Markdown is not valid UTF-8: {member_name}"
        ) from error
    if not content.strip():
        raise SessionImportError(f"Saved Markdown is empty: {member_name}")
    return content


def _read_manifest(
    archive: zipfile.ZipFile,
    member_name: str,
) -> Mapping[str, Any]:
    try:
        payload = json.loads(archive.read(member_name).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SessionImportError("Tumor-board manifest is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise SessionImportError("Tumor-board manifest must be a JSON object.")
    return payload


def _read_review_packet(
    archive: zipfile.ZipFile,
    member_name: str,
) -> ReviewPacketExport:
    """Read and validate one persisted review packet without extraction.

    Acceptance criteria:
        1. Accepts only UTF-8 JSON matching `ReviewPacketExport`.
        2. Does not mutate archive data or write to the filesystem.
        3. Raises a bounded domain error without returning packet content.
    """
    try:
        content = archive.read(member_name).decode("utf-8")
        return ReviewPacketExport.model_validate_json(content)
    except (UnicodeDecodeError, ValidationError) as error:
        raise SessionImportError(
            "Saved review packet is not valid ReviewPacketExport JSON."
        ) from error


def _validated_review_packet_session(
    packet: ReviewPacketExport,
    selected_session_id: str,
) -> str:
    """Return a coherent session ID for the archive and review packet.

    Acceptance criteria:
        1. Packet and bundle session identifiers must match.
        2. Explicit archive session identifiers must match the packet.
        3. Rootless generically named archives use the validated packet ID.
    """
    packet_session_id = packet.session_id.strip()
    if not packet_session_id or packet.bundle.session_id != packet_session_id:
        raise SessionImportError(
            "Saved review packet contains inconsistent session identifiers."
        )
    if (
        selected_session_id != "imported_session"
        and selected_session_id != packet_session_id
    ):
        raise SessionImportError(
            "Saved review packet session does not match the pathway session."
        )
    return packet_session_id


def _verify_manifest_hash(
    manifest: Mapping[str, Any],
    field_name: str,
    content: str,
) -> None:
    expected = manifest.get(field_name)
    if expected is None:
        return
    if not isinstance(expected, str) or len(expected) != 64:
        raise SessionImportError(f"Tumor-board manifest has an invalid {field_name}.")
    canonical_content = content.strip()
    actual = hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()
    if actual != expected.casefold():
        raise SessionImportError(f"Saved artifact failed {field_name} verification.")


def _session_id_from_archive_stem(archive_stem: str) -> str:
    normalized = archive_stem.strip()
    return normalized if normalized.startswith("session_") else "imported_session"
