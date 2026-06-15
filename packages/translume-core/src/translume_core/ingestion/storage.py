from __future__ import annotations

import hashlib
from pathlib import Path

from translume_schemas.session import CaseSession, StoredFile


def persist_uploaded_pdf(
    session: CaseSession,
    filename: str,
    content: bytes,
    storage_root: Path,
) -> StoredFile:
    """Persist an uploaded PDF and return source-file metadata.

    Acceptance criteria:
        1. Raw file is persisted before extraction.
        2. Empty file raises `ValueError`.
        3. Non-PDF input raises `ValueError`.
        4. Same bytes produce same SHA-256 hash.
        5. Filesystem writes are isolated to this boundary function.

    Args:
        session: Active case session.
        filename: Original uploaded filename.
        content: Raw uploaded bytes.
        storage_root: Root directory for file storage.

    Returns:
        Stored file metadata.

    Raises:
        ValueError: If filename or content are invalid.
    """
    if not content:
        raise ValueError("uploaded PDF content is empty")
    if not filename.lower().endswith(".pdf"):
        raise ValueError(f"uploaded file is not a PDF: {filename!r}")
    digest = hashlib.sha256(content).hexdigest()
    source_file_id = f"file_{digest[:24]}"
    directory = storage_root / session.case_id / session.session_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source_file_id}.pdf"
    path.write_bytes(content)
    return StoredFile(
        case_id=session.case_id,
        session_id=session.session_id,
        source_file_id=source_file_id,
        filename=filename,
        path=path,
        size_bytes=len(content),
        sha256=digest,
    )
