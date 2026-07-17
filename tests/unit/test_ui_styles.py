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
