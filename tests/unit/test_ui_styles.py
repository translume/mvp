from translume_ui.styles import TRANSLUME_CSS, header_html


def test_tab_buttons_have_opaque_readable_states() -> None:
    """Require explicit background and text colors for tab interaction states."""
    assert 'button[role="tab"] {' in TRANSLUME_CSS
    assert 'button[role="tab"]:hover' in TRANSLUME_CSS
    assert 'button[role="tab"]:focus-visible' in TRANSLUME_CSS
    assert 'button[role="tab"][aria-selected="true"] {' in TRANSLUME_CSS
    assert "background: #ffffff !important;" in TRANSLUME_CSS
    assert "background: #e5e7eb !important;" in TRANSLUME_CSS
    assert "background: #1f2937 !important;" in TRANSLUME_CSS
    assert "color: #000000 !important;" in TRANSLUME_CSS
    assert "color: #ffffff !important;" in TRANSLUME_CSS
    assert "opacity: 1 !important;" in TRANSLUME_CSS


def test_markdown_text_and_links_have_readable_colors() -> None:
    """Require stable visible colors for rendered Markdown and its links."""
    assert ".gradio-container .prose * {" in TRANSLUME_CSS
    assert "color: #111827 !important;" in TRANSLUME_CSS
    assert ".gradio-container .prose a {" in TRANSLUME_CSS
    assert ".gradio-container .prose a:hover" in TRANSLUME_CSS
    assert ".gradio-container .prose a:focus-visible" in TRANSLUME_CSS


def test_clinical_review_markdown_text_color_is_scoped() -> None:
    """Change Markdown foreground only inside the clinical-review tab."""
    assert "#clinical-review-tab .prose," in TRANSLUME_CSS
    assert "#clinical-review-tab .prose * {" in TRANSLUME_CSS
    scoped_rule = TRANSLUME_CSS.split(
        "#clinical-review-tab .prose,",
        maxsplit=1,
    )[1].split("}", maxsplit=1)[0]
    assert "color: #f9fafb !important;" in scoped_rule
    assert "opacity: 1 !important;" in scoped_rule


def test_clinical_review_decision_card_background_is_scoped() -> None:
    """Use a dark card background only within the clinical-review tab."""
    selector = "#clinical-review-tab .translume-decision-card {"
    assert selector in TRANSLUME_CSS
    scoped_rule = TRANSLUME_CSS.split(selector, maxsplit=1)[1].split(
        "}",
        maxsplit=1,
    )[0]
    assert (
        "background: linear-gradient(180deg, #374151, #1f2937) !important;"
        in scoped_rule
    )


def test_clinical_review_inline_code_background_is_dark_and_scoped() -> None:
    """Keep white Clinical-review badge text visible on a dark background."""
    assert "#clinical-review-tab .md :not(pre) > code," in TRANSLUME_CSS
    assert "#clinical-review-tab .prose :not(pre) > code {" in TRANSLUME_CSS
    assert "background: #374151 !important;" in TRANSLUME_CSS
    assert "border-color: #4b5563 !important;" in TRANSLUME_CSS


def test_evidence_detail_markdown_colors_are_component_scoped() -> None:
    """Limit light evidence text to the two requested Markdown boxes."""
    assert "#medea-reasoning-content .prose," in TRANSLUME_CSS
    assert "#medea-reasoning-content .prose :not(code)," in TRANSLUME_CSS
    assert "#evidence-gaps-content .prose," in TRANSLUME_CSS
    assert "#evidence-gaps-content .prose :not(code) {" in TRANSLUME_CSS


def test_technical_audit_heading_colors_are_table_scoped() -> None:
    """Limit visible audit labels to the three technical tables."""
    assert "#technical-validation-table:is(" in TRANSLUME_CSS
    assert "#technical-validation-table :is(" in TRANSLUME_CSS
    assert "#technical-provenance-table:is(" in TRANSLUME_CSS
    assert "#technical-provenance-table :is(" in TRANSLUME_CSS
    assert "#technical-ledger-table:is(" in TRANSLUME_CSS
    assert "#technical-ledger-table :is(" in TRANSLUME_CSS
    assert '[data-testid="block-info"]' in TRANSLUME_CSS


def test_inline_markdown_code_has_pale_high_contrast_colors() -> None:
    """Require pale backgrounds and dark text for inline Markdown code."""
    assert ".gradio-container .md :not(pre) > code" in TRANSLUME_CSS
    assert ".gradio-container .prose :not(pre) > code" in TRANSLUME_CSS
    assert "background: #d9e0ff !important;" in TRANSLUME_CSS
    assert "color: #111827 !important;" in TRANSLUME_CSS
    assert "border: 1px solid #c7d2fe !important;" in TRANSLUME_CSS


def test_saved_session_status_has_scoped_visible_text() -> None:
    """Require visible text without changing unrelated status components."""
    assert "#session-import-status .translume-status," in TRANSLUME_CSS
    assert "#session-import-status .translume-status * {" in TRANSLUME_CSS
    assert "color: #f9fafb !important;" in TRANSLUME_CSS


def test_tab_overflow_dots_are_blue_only_when_not_hovered() -> None:
    """Require a visible idle icon without overriding its hover state."""
    selector = '.tab-nav button:not([role="tab"]):not(:hover)'
    assert f"{selector} {{" in TRANSLUME_CSS
    assert f"{selector} svg {{" in TRANSLUME_CSS
    assert "color: var(--translume-indigo) !important;" in TRANSLUME_CSS
    assert "fill: currentColor !important;" in TRANSLUME_CSS


def test_workflow_error_text_has_scoped_visible_color() -> None:
    """Require readable error text in the conditional workflow panel."""
    assert "#workflow-error .translume-error," in TRANSLUME_CSS
    assert "#workflow-error .translume-error * {" in TRANSLUME_CSS
    assert "color: var(--translume-danger) !important;" in TRANSLUME_CSS


def test_pathway_processing_status_is_visible_and_readable() -> None:
    """Require a dedicated readable timer target on the pathway tab."""
    assert "#pathway-processing-status {" in TRANSLUME_CSS
    assert ".translume-pathway-processing {" in TRANSLUME_CSS
    assert "border-left: 5px solid var(--translume-blue);" in TRANSLUME_CSS
    assert "color: #111827;" in TRANSLUME_CSS


def test_header_omits_removed_badges() -> None:
    """Require the header copy while omitting the three retired badges."""
    rendered = header_html()
    assert "Oncologist Cockpit" in rendered
    assert "Private local models" not in rendered
    assert "Clinician decision support" not in rendered
    assert "Human validation required" not in rendered
    assert "translume-badges" not in rendered
    assert ".translume-badges" not in TRANSLUME_CSS
    assert ".translume-badge" not in TRANSLUME_CSS
