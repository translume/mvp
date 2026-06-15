from __future__ import annotations

from translume_schemas.document import DocumentChunk
from translume_schemas.export import ClinicalArtifactBundle, ReviewPacketExport


def build_review_packet_export(
    bundle: ClinicalArtifactBundle,
    chunks: list[DocumentChunk],
    source_file_id: str,
) -> ReviewPacketExport:
    """Create an exportable review packet.

    Acceptance criteria:
        1. Export includes raw source_file_id.
        2. Export includes structured artifacts and evidence artifacts in bundle.
        3. Export includes source chunks.
        4. Export includes validation decisions and ledger events through bundle.
        5. Export is JSON-serializable.
        6. Function is pure.
    """
    return ReviewPacketExport(
        case_id=bundle.case_id,
        session_id=bundle.session_id,
        source_file_id=source_file_id,
        chunks=chunks,
        bundle=bundle,
    )
