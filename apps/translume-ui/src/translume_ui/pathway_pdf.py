from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)


_SAFE_FILENAME: Final = re.compile(r"[^A-Za-z0-9_.-]+")
_TABLE_SEPARATOR: Final = re.compile(r"^:?-{3,}:?$")


@dataclass(frozen=True)
class PathwayPDFSection:
    """Represent one complete Markdown section rendered in the pathway tab.

    Acceptance criteria:
        1. Stores the displayed title and Markdown without transformation.
        2. Remains immutable after construction.
    """

    title: str
    markdown: str


@dataclass(frozen=True)
class MarkdownBlock:
    """Represent one safe, renderer-independent Markdown block."""

    kind: Literal["heading", "paragraph", "bullet_list", "code", "table"]
    value: str | tuple[str, ...] | tuple[tuple[str, ...], ...]
    level: int = 0


def normalize_pathway_sections(
    pathway_markdown: str,
    research_markdown: str,
    tumor_board_markdown: str,
) -> tuple[PathwayPDFSection, ...]:
    """Return the three pathway-tab sections in display order.

    Acceptance criteria:
        1. Preserves every input character in the corresponding section.
        2. Returns all sections, including empty sections.
        3. Does not mutate caller-owned strings.
    """
    return (
        PathwayPDFSection("Pathway analysis", pathway_markdown),
        PathwayPDFSection("Research memo", research_markdown),
        PathwayPDFSection("Tumor-board causal summary", tumor_board_markdown),
    )


def parse_markdown_blocks(markdown: str) -> tuple[MarkdownBlock, ...]:
    """Parse supported Markdown while retaining unsupported content as text.

    Acceptance criteria:
        1. Recognizes headings, paragraphs, lists, fenced code, and tables.
        2. Preserves source order and all non-syntax text.
        3. Treats raw HTML as inert text.
        4. Returns the same blocks for the same input.
    """
    lines = markdown.splitlines()
    blocks: list[MarkdownBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.lstrip().startswith("```"):
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1 if index < len(lines) else 0
            blocks.append(MarkdownBlock("code", "\n".join(code_lines)))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            blocks.append(
                MarkdownBlock(
                    "heading",
                    heading.group(2),
                    level=len(heading.group(1)),
                )
            )
            index += 1
            continue
        if _is_table_start(lines, index):
            rows, index = _consume_table(lines, index)
            blocks.append(MarkdownBlock("table", rows))
            continue
        if _list_item(line) is not None:
            items: list[str] = []
            while index < len(lines):
                item = _list_item(lines[index])
                if item is None:
                    break
                items.append(item)
                index += 1
            blocks.append(MarkdownBlock("bullet_list", tuple(items)))
            continue
        paragraph = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip():
            if (
                re.match(r"^#{1,6}\s+", lines[index])
                or lines[index].lstrip().startswith("```")
                or _list_item(lines[index]) is not None
                or _is_table_start(lines, index)
            ):
                break
            paragraph.append(lines[index].strip())
            index += 1
        blocks.append(MarkdownBlock("paragraph", "\n".join(paragraph)))
    return tuple(blocks)


def safe_pdf_filename(session_id: str) -> str:
    """Return a bounded PDF filename derived from an untrusted session ID.

    Acceptance criteria:
        1. Produces only a basename with a .pdf suffix.
        2. Replaces unsafe runs with one hyphen.
        3. Uses `session` when no safe identifier remains.
    """
    safe_session = _SAFE_FILENAME.sub("-", session_id.strip()).strip("-._")
    safe_session = safe_session[:96] or "session"
    return f"translume-pathway-analysis-{safe_session}.pdf"


def build_pathway_pdf(
    output_path: Path,
    *,
    session_id: str,
    sections: tuple[PathwayPDFSection, ...],
    generated_at: datetime | None = None,
) -> Path:
    """Build a paginated local PDF containing every pathway-tab section.

    Acceptance criteria:
        1. Writes a valid PDF to the requested path.
        2. Includes every section in input order.
        3. Renders empty sections explicitly as unavailable.
        4. Escapes content before ReportLab paragraph interpretation.
        5. Does not perform network access or mutate section inputs.
    """
    timestamp = generated_at or datetime.now(timezone.utc)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _document_styles()
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.65 * inch,
        title="Translume Pathway Analysis",
        author="Translume",
    )
    story: list[object] = [
        Paragraph("Translume Pathway Analysis", styles["Title"]),
        Paragraph(
            f"Session: {html.escape(session_id.strip() or 'Unavailable')}",
            styles["Meta"],
        ),
        Paragraph(
            f"Generated: {html.escape(timestamp.astimezone(timezone.utc).isoformat())}",
            styles["Meta"],
        ),
        Spacer(1, 12),
        Paragraph(
            "Clinician decision support only. This document requires oncology "
            "review and does not establish diagnosis, treatment response, cure, "
            "survival benefit, or a deterministic outcome.",
            styles["Disclaimer"],
        ),
        PageBreak(),
    ]
    for section_index, section in enumerate(sections):
        if section_index:
            story.append(PageBreak())
        story.append(Paragraph(html.escape(section.title), styles["SectionTitle"]))
        blocks = parse_markdown_blocks(section.markdown)
        if not blocks:
            story.append(Paragraph("No information is available.", styles["BodyText"]))
        else:
            for block in blocks:
                story.extend(_block_flowables(block, styles))
    document.build(
        story,
        onFirstPage=_page_footer(session_id),
        onLaterPages=_page_footer(session_id),
    )
    return output_path


def write_pathway_pdf(
    output_root: Path,
    *,
    session_id: str,
    sections: tuple[PathwayPDFSection, ...],
) -> Path:
    """Atomically write a user-requested pathway PDF under the export root.

    Acceptance criteria:
        1. Writes only beneath the supplied export root.
        2. Atomically replaces an earlier export with the same filename.
        3. Removes the temporary file when generation fails.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / safe_pdf_filename(session_id)
    temporary = destination.with_suffix(".tmp.pdf")
    try:
        build_pathway_pdf(
            temporary,
            session_id=session_id,
            sections=sections,
        )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _document_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "TranslumeTitle",
            parent=styles["Title"],
            textColor=colors.HexColor("#111827"),
            alignment=TA_CENTER,
        ),
        "SectionTitle": ParagraphStyle(
            "TranslumeSectionTitle",
            parent=styles["Heading1"],
            textColor=colors.HexColor("#4f46e5"),
            spaceAfter=12,
        ),
        "Heading": ParagraphStyle(
            "TranslumeHeading",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#111827"),
            spaceBefore=8,
            spaceAfter=5,
        ),
        "BodyText": ParagraphStyle(
            "TranslumeBody",
            parent=styles["BodyText"],
            textColor=colors.HexColor("#111827"),
            leading=14,
            spaceAfter=7,
            splitLongWords=True,
        ),
        "Code": ParagraphStyle(
            "TranslumeCode",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            backColor=colors.HexColor("#d9e0ff"),
            borderPadding=6,
            spaceAfter=8,
        ),
        "Meta": ParagraphStyle(
            "TranslumeMeta",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#5f6b7a"),
        ),
        "Disclaimer": ParagraphStyle(
            "TranslumeDisclaimer",
            parent=styles["BodyText"],
            backColor=colors.HexColor("#f7f9fc"),
            borderColor=colors.HexColor("#6d28d9"),
            borderWidth=1,
            borderPadding=8,
        ),
    }


def _block_flowables(
    block: MarkdownBlock,
    styles: dict[str, ParagraphStyle],
) -> list[object]:
    if block.kind == "heading":
        return [Paragraph(html.escape(str(block.value)), styles["Heading"])]
    if block.kind == "paragraph":
        value = html.escape(str(block.value)).replace("\n", "<br/>")
        return [Paragraph(value, styles["BodyText"])]
    if block.kind == "code":
        return [XPreformatted(html.escape(str(block.value)), styles["Code"])]
    if block.kind == "bullet_list":
        values = tuple(block.value)
        items = [
            ListItem(Paragraph(html.escape(value), styles["BodyText"]))
            for value in values
        ]
        return [ListFlowable(items, bulletType="bullet", leftIndent=18), Spacer(1, 5)]
    rows = tuple(block.value)
    table_data = [
        [Paragraph(html.escape(cell), styles["BodyText"]) for cell in row]
        for row in rows
    ]
    table = Table(table_data, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e0ff")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe4ef")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return [table, Spacer(1, 8)]


def _page_footer(session_id: str):
    safe_session = session_id.strip() or "Unavailable"

    def draw(canvas: Canvas, document: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5f6b7a"))
        canvas.drawString(0.65 * inch, 0.35 * inch, safe_session[:80])
        canvas.drawRightString(
            letter[0] - 0.65 * inch,
            0.35 * inch,
            f"Page {document.page}",
        )
        canvas.restoreState()

    return draw


def _list_item(line: str) -> str | None:
    match = re.match(r"^\s*(?:[-*+] |\d+[.)] )(.*)$", line)
    return match.group(1).strip() if match else None


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return False
    separators = _table_cells(lines[index + 1])
    return bool(separators) and all(_TABLE_SEPARATOR.match(cell) for cell in separators)


def _consume_table(
    lines: list[str],
    index: int,
) -> tuple[tuple[tuple[str, ...], ...], int]:
    rows = [_table_cells(lines[index])]
    index += 2
    while index < len(lines) and "|" in lines[index] and lines[index].strip():
        rows.append(_table_cells(lines[index]))
        index += 1
    width = max(len(row) for row in rows)
    normalized = tuple(tuple([*row, *([""] * (width - len(row)))]) for row in rows)
    return normalized, index


def _table_cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
