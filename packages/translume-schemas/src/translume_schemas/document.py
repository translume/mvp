from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class BoundingBox(TranslumeBaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class DocumentBlock(TranslumeBaseModel):
    block_id: str
    page_number: int
    block_type: str
    text: str
    order_index: int
    bbox: BoundingBox | None = None
    confidence: float | None = None


class DocumentTable(TranslumeBaseModel):
    table_id: str
    page_number: int
    rows: list[list[str]]
    text: str
    bbox: BoundingBox | None = None


class DocumentPage(TranslumeBaseModel):
    page_number: int
    text: str
    blocks: list[DocumentBlock]
    tables: list[DocumentTable]
    warnings: list[str] = []


class DocumentExtractionOutput(TranslumeBaseModel):
    source_file_id: str
    extraction_method: str
    pages: list[DocumentPage]
    warnings: list[str] = []
    quality_score: float | None = None
    needs_human_review: bool = False


class ExtractionQualityReport(TranslumeBaseModel):
    source_file_id: str
    quality_score: float
    pages_with_text: int
    pages_with_warnings: int
    table_count: int
    warnings: list[str]
    needs_human_review: bool


class DetectedSection(TranslumeBaseModel):
    section_id: str
    label: str
    page_start: int
    page_end: int
    block_start: int
    block_end: int


class DocumentChunk(TranslumeBaseModel):
    chunk_id: str
    case_id: str
    session_id: str
    source_file_id: str
    report_type: str
    page_start: int
    page_end: int
    section: str
    chunk_type: str
    source_text: str
    source_block_ids: list[str]
    bbox: BoundingBox | None = None
    needs_human_review: bool
