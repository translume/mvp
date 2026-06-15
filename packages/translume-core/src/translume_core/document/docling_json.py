from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from translume_schemas.document import (
    BoundingBox,
    DocumentBlock,
    DocumentExtractionOutput,
    DocumentPage,
    DocumentTable,
)


class DoclingJsonError(ValueError):
    """Raised when Docling JSON cannot be normalized."""


@dataclass(frozen=True)
class _ExtractedItem:
    """Internal normalized Docling item.

    Attributes:
        path: Stable traversal path in the exported Docling JSON.
        page_number: One-indexed page number.
        label: Raw Docling label or inferred label.
        text: Extracted item text.
        bbox: Optional page-space bounding box.
        confidence: Optional confidence value from source metadata.
        order_index: Stable order index.
    """

    path: str
    page_number: int
    label: str
    text: str
    bbox: BoundingBox | None
    confidence: float | None
    order_index: int


def docling_dict_to_document_extraction(
    exported: Mapping[str, Any],
    *,
    source_file_id: str,
    extraction_method: str,
) -> DocumentExtractionOutput:
    """Normalize exported Docling JSON into Translume document schemas.

    Acceptance criteria:
        1. Determinism: The same exported document returns the same blocks,
           tables, pages, and warning values.
        2. No mutation: The exported mapping is not modified.
        3. Page preservation: Page numbers are inferred from Docling
           provenance whenever available.
        4. Layout preservation: Text, labels, confidence, and bounding boxes are
           preserved when Docling exports them.
        5. Table preservation: Table-like items are emitted as DocumentTable
           records as well as source blocks for chunking.
        6. Non-clinical: No biomedical or clinical interpretation is performed.
        7. Validation: Missing source_file_id or extraction_method raises
           ValueError.

    Args:
        exported: Dict produced by `DoclingDocument.export_to_dict()`.
        source_file_id: Stored source file identifier.
        extraction_method: Method label, such as `docling` or
            `granite_docling`.

    Returns:
        Translume document extraction output.

    Raises:
        ValueError: If required identifiers are empty.
    """
    if not source_file_id.strip():
        raise ValueError("source_file_id is required")
    if not extraction_method.strip():
        raise ValueError("extraction_method is required")
    items = _collect_items(exported)
    page_numbers = _page_numbers(exported, items)
    pages = [
        _page_from_items(
            source_file_id=source_file_id,
            page_number=page_number,
            items=[item for item in items if item.page_number == page_number],
        )
        for page_number in page_numbers
    ]
    warnings = _document_warnings(pages)
    return DocumentExtractionOutput(
        source_file_id=source_file_id,
        extraction_method=extraction_method,
        pages=pages,
        warnings=warnings,
        quality_score=None,
        needs_human_review=bool(warnings),
    )


def _collect_items(exported: Mapping[str, Any]) -> list[_ExtractedItem]:
    raw_items = list(_iter_candidate_items(exported, path="root"))
    items: list[_ExtractedItem] = []
    for order_index, (path, node) in enumerate(raw_items):
        text = _node_text(node)
        if not text:
            continue
        prov = _first_provenance(node)
        page_number = _page_number_from_provenance(prov)
        label = str(node.get("label") or node.get("type") or "text")
        items.append(
            _ExtractedItem(
                path=path,
                page_number=page_number,
                label=label,
                text=text,
                bbox=_bbox_from_provenance(prov),
                confidence=_confidence_from_node(node),
                order_index=order_index,
            )
        )
    return sorted(items, key=lambda item: (item.page_number, item.order_index, item.path))


def _iter_candidate_items(
    value: Any,
    *,
    path: str,
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        text = _node_text(value)
        if text and _looks_like_docling_content(value):
            yield path, value
        for key in sorted(value.keys(), key=str):
            yield from _iter_candidate_items(value[key], path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            yield from _iter_candidate_items(item, path=f"{path}[{index}]")


def _looks_like_docling_content(node: Mapping[str, Any]) -> bool:
    return any(key in node for key in ("prov", "label", "type", "data", "text"))


def _node_text(node: Mapping[str, Any]) -> str:
    direct = node.get("text") or node.get("orig") or node.get("caption")
    if isinstance(direct, str) and direct.strip():
        return _normalize_text(direct)
    data = node.get("data")
    if isinstance(data, Mapping):
        cell_text = _table_cell_text(data)
        if cell_text:
            return cell_text
    return ""


def _table_cell_text(data: Mapping[str, Any]) -> str:
    cells = data.get("table_cells") or data.get("cells")
    if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes, bytearray)):
        return ""
    texts: list[str] = []
    for cell in cells:
        if isinstance(cell, Mapping):
            value = cell.get("text") or cell.get("content")
            if isinstance(value, str) and value.strip():
                texts.append(_normalize_text(value))
    return " | ".join(texts)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _first_provenance(node: Mapping[str, Any]) -> Mapping[str, Any]:
    prov = node.get("prov") or node.get("provenance")
    if isinstance(prov, Sequence) and not isinstance(prov, (str, bytes, bytearray)):
        for item in prov:
            if isinstance(item, Mapping):
                return item
    if isinstance(prov, Mapping):
        return prov
    return {}


def _page_number_from_provenance(prov: Mapping[str, Any]) -> int:
    value = prov.get("page_no") or prov.get("page") or prov.get("page_number")
    try:
        page_number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, page_number)


def _bbox_from_provenance(prov: Mapping[str, Any]) -> BoundingBox | None:
    bbox = prov.get("bbox") or prov.get("bounding_box")
    if not isinstance(bbox, Mapping):
        return None
    aliases = (
        ("x1", "y1", "x2", "y2"),
        ("l", "t", "r", "b"),
        ("left", "top", "right", "bottom"),
    )
    for keys in aliases:
        if all(key in bbox for key in keys):
            try:
                return BoundingBox(
                    x1=float(bbox[keys[0]]),
                    y1=float(bbox[keys[1]]),
                    x2=float(bbox[keys[2]]),
                    y2=float(bbox[keys[3]]),
                )
            except (TypeError, ValueError):
                return None
    return None


def _confidence_from_node(node: Mapping[str, Any]) -> float | None:
    value = node.get("confidence") or node.get("conf") or node.get("score")
    try:
        if value is None:
            return None
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, confidence))


def _page_numbers(exported: Mapping[str, Any], items: Sequence[_ExtractedItem]) -> list[int]:
    pages = exported.get("pages")
    numbers: set[int] = set()
    if isinstance(pages, Mapping):
        for key in pages:
            try:
                numbers.add(max(1, int(key)))
            except (TypeError, ValueError):
                continue
    elif isinstance(pages, Sequence) and not isinstance(pages, (str, bytes, bytearray)):
        numbers.update(range(1, len(pages) + 1))
    numbers.update(item.page_number for item in items)
    return sorted(numbers or {1})


def _page_from_items(
    *,
    source_file_id: str,
    page_number: int,
    items: Sequence[_ExtractedItem],
) -> DocumentPage:
    blocks = [
        DocumentBlock(
            block_id=_stable_id(source_file_id, item.path, "block"),
            page_number=page_number,
            block_type=_block_type(item.label),
            text=item.text,
            order_index=index,
            bbox=item.bbox,
            confidence=item.confidence,
        )
        for index, item in enumerate(items)
    ]
    tables = [
        DocumentTable(
            table_id=_stable_id(source_file_id, item.path, "table"),
            page_number=page_number,
            rows=_rows_from_table_text(item.text),
            text=item.text,
            bbox=item.bbox,
        )
        for item in items
        if _block_type(item.label) == "table"
    ]
    text = "\n".join(block.text for block in blocks if block.text.strip())
    warnings = [] if text.strip() else ["page_has_no_extractable_text"]
    return DocumentPage(
        page_number=page_number,
        text=text,
        blocks=blocks,
        tables=tables,
        warnings=warnings,
    )


def _block_type(label: str) -> str:
    normalized = "_".join(label.casefold().strip().replace("-", "_").split())
    if "table" in normalized:
        return "table"
    if normalized in {"section_header", "title", "heading", "header"}:
        return "heading"
    if "list" in normalized:
        return "list"
    return normalized or "text"


def _rows_from_table_text(text: str) -> list[list[str]]:
    rows = []
    for raw_row in text.split("\n"):
        cells = [cell.strip() for cell in raw_row.split("|") if cell.strip()]
        if cells:
            rows.append(cells)
    return rows or [[text]]


def _stable_id(source_file_id: str, path: str, kind: str) -> str:
    return f"{kind}_{uuid5(NAMESPACE_URL, f'{source_file_id}:{kind}:{path}').hex[:16]}"


def _document_warnings(pages: Sequence[DocumentPage]) -> list[str]:
    return [
        f"page_{page.page_number}:{warning}"
        for page in pages
        for warning in page.warnings
    ]
