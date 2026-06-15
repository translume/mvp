from __future__ import annotations

import json
import os
from typing import Any

import gradio as gr
import httpx

API_BASE_URL = os.getenv("TRANSLUME_API_BASE_URL", "http://translume-api:8000").rstrip("/")
PROCESS_URL = f"{API_BASE_URL}/api/v1/reports/process"


def process_pdf(file_path: str, report_type: str) -> tuple[str, str, list[list[str]], object]:
    """Upload a PDF to the API and return packet JSON plus claim cards.

    Acceptance criteria:
        1. Sends the uploaded PDF to FastAPI.
        2. Does not fabricate review content in the UI.
        3. Returns API errors transparently.
        4. Extracts validation-card choices from the API response only.
    """
    if not file_path:
        return "Upload a PDF first.", "", [], gr.update(choices=[], value=None)
    with open(file_path, "rb") as handle:
        files = {"file": (file_path, handle, "application/pdf")}
        data = {"report_type": report_type}
        try:
            response = httpx.post(PROCESS_URL, files=files, data=data, timeout=600)
        except httpx.HTTPError as error:
            return f"API request failed: {error}", "", [], gr.update(choices=[], value=None)
    if response.status_code >= 400:
        return f"API error {response.status_code}: {response.text}", "", [], gr.update(choices=[], value=None)
    packet = response.json()
    session_id = str(packet.get("session_id", ""))
    rows = _claim_rows(packet)
    choices = [row[0] for row in rows]
    return (
        json.dumps(packet, indent=2),
        session_id,
        rows,
        gr.update(choices=choices, value=choices[0] if choices else None),
    )


def submit_validation(
    session_id: str,
    claim_id: str,
    status: str,
    reviewer_id: str,
    reviewer_note: str,
) -> tuple[str, list[list[str]], object]:
    """Submit a claim validation decision to the API.

    Acceptance criteria:
        1. Requires a stored session ID and real claim ID.
        2. Calls the validation API endpoint.
        3. Returns updated claim cards from the API response only.
        4. Does not update UI state optimistically or fabricate decisions.
    """
    if not session_id:
        return "No processed review packet session is available.", [], gr.update(choices=[], value=None)
    if not claim_id:
        return "Select a claim to validate.", [], gr.update(choices=[], value=None)
    payload = {
        "status": status,
        "reviewer_id": reviewer_id or None,
        "reviewer_note": reviewer_note or None,
    }
    url = f"{API_BASE_URL}/api/v1/review-packets/{session_id}/claims/{claim_id}/validation"
    try:
        response = httpx.post(url, json=payload, timeout=120)
    except httpx.HTTPError as error:
        return f"API request failed: {error}", [], gr.update(choices=[], value=None)
    if response.status_code >= 400:
        return f"API error {response.status_code}: {response.text}", [], gr.update(choices=[], value=None)
    data = response.json()
    rows = _claim_rows({"bundle": {"claims": data.get("claims", [])}})
    choices = [row[0] for row in rows]
    return (
        json.dumps(data, indent=2),
        rows,
        gr.update(choices=choices, value=claim_id if claim_id in choices else None),
    )


def fetch_export(session_id: str) -> str:
    """Fetch the persisted review packet export from the API."""
    if not session_id:
        return "No processed review packet session is available."
    url = f"{API_BASE_URL}/api/v1/review-packets/{session_id}/export"
    try:
        response = httpx.get(url, timeout=120)
    except httpx.HTTPError as error:
        return f"API request failed: {error}"
    if response.status_code >= 400:
        return f"API error {response.status_code}: {response.text}"
    return json.dumps(response.json(), indent=2)


def build_app() -> gr.Blocks:
    """Build the Gradio oncologist cockpit."""
    with gr.Blocks(title="Translume Oncologist Cockpit") as demo:
        gr.Markdown("# Translume Oncologist Cockpit")
        gr.Markdown(
            "Upload one oncology report to generate a source-backed, "
            "reviewable tumor-behavior intelligence packet. Then validate "
            "claim cards as a human reviewer."
        )
        session_state = gr.State("")
        with gr.Row():
            report = gr.File(label="Oncology PDF", file_types=[".pdf"], type="filepath")
            report_type = gr.Dropdown(
                choices=["NGS", "WGS", "FISH", "IHC", "RESEARCH_PDF", "XT", "XR", "RNA"],
                value="NGS",
                label="Report type",
            )
        run = gr.Button("Generate review packet")
        output = gr.Code(label="Review packet JSON", language="json")
        claims_table = gr.Dataframe(
            headers=["claim_id", "status", "class", "claim", "evidence", "limitations"],
            label="Claim validation cards",
            interactive=False,
        )
        claim_selector = gr.Dropdown(choices=[], label="Claim to validate")
        with gr.Row():
            status = gr.Dropdown(
                choices=["validated", "rejected", "needs_review"],
                value="needs_review",
                label="Validation decision",
            )
            reviewer_id = gr.Textbox(label="Reviewer ID")
        reviewer_note = gr.Textbox(label="Reviewer note", lines=3)
        validate = gr.Button("Save validation decision")
        validation_output = gr.Code(label="Validation API response", language="json")
        fetch = gr.Button("Fetch persisted review packet export")
        persisted_output = gr.Code(label="Persisted review packet JSON", language="json")
        run.click(
            process_pdf,
            inputs=[report, report_type],
            outputs=[output, session_state, claims_table, claim_selector],
        )
        validate.click(
            submit_validation,
            inputs=[session_state, claim_selector, status, reviewer_id, reviewer_note],
            outputs=[validation_output, claims_table, claim_selector],
        )
        fetch.click(fetch_export, inputs=[session_state], outputs=persisted_output)
    return demo


def _claim_rows(packet: dict[str, Any]) -> list[list[str]]:
    claims = packet.get("bundle", {}).get("claims", [])
    return [
        [
            str(claim.get("claim_id", "")),
            str(claim.get("validation_status", "")),
            str(claim.get("claim_class", "")),
            str(claim.get("claim", "")),
            str(claim.get("evidence_source", "")),
            str(claim.get("limitations", "")),
        ]
        for claim in claims
    ]


if __name__ == "__main__":
    build_app().launch(server_name="0.0.0.0", server_port=7860)
