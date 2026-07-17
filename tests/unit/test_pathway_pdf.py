from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_ui.pathway_pdf import (
    build_pathway_pdf,
    normalize_pathway_sections,
    parse_markdown_blocks,
    safe_pdf_filename,
    write_pathway_pdf,
)


def test_parse_markdown_blocks_preserves_supported_content_order() -> None:
    markdown = """# Heading

Body with <script>inert</script> content.

- First
- Second

```text
value < 2
```

| Gene | State |
| --- | --- |
| EGFR | altered |
"""

    blocks = parse_markdown_blocks(markdown)

    assert [block.kind for block in blocks] == [
        "heading",
        "paragraph",
        "bullet_list",
        "code",
        "table",
    ]
    assert blocks[1].value == "Body with <script>inert</script> content."
    assert blocks[2].value == ("First", "Second")
    assert blocks[4].value == (
        ("Gene", "State"),
        ("EGFR", "altered"),
    )


def test_build_pathway_pdf_writes_valid_multi_section_document(tmp_path) -> None:
    sections = normalize_pathway_sections(
        "# Pathway\nPathway content & evidence.",
        "# Research\n- Study one\n- Study two",
        "# Tumor board\n| Claim | Status |\n| --- | --- |\n| A | Review |",
    )

    output = build_pathway_pdf(
        tmp_path / "pathway.pdf",
        session_id="session_123",
        sections=sections,
        generated_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    data = output.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 2_000
    assert sections == normalize_pathway_sections(
        "# Pathway\nPathway content & evidence.",
        "# Research\n- Study one\n- Study two",
        "# Tumor board\n| Claim | Status |\n| --- | --- |\n| A | Review |",
    )


def test_write_pathway_pdf_uses_safe_atomic_destination(tmp_path) -> None:
    output = write_pathway_pdf(
        tmp_path,
        session_id="../../session unsafe",
        sections=normalize_pathway_sections("Pathway", "", ""),
    )

    assert output.parent == tmp_path
    assert output.name == "translume-pathway-analysis-session-unsafe.pdf"
    assert output.read_bytes().startswith(b"%PDF-")
    assert not list(tmp_path.glob("*.tmp.pdf"))


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        ("session_123", "translume-pathway-analysis-session_123.pdf"),
        ("", "translume-pathway-analysis-session.pdf"),
        ("../a b", "translume-pathway-analysis-a-b.pdf"),
    ],
)
def test_safe_pdf_filename(session_id: str, expected: str) -> None:
    assert safe_pdf_filename(session_id) == expected


def test_invalid_pdf_output_does_not_leave_temporary_file(tmp_path) -> None:
    output_root = tmp_path / "not-a-directory"
    output_root.write_text("occupied", encoding="utf-8")

    with pytest.raises(OSError):
        write_pathway_pdf(
            output_root,
            session_id="session",
            sections=normalize_pathway_sections("Pathway", "", ""),
        )
