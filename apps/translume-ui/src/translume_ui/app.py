from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import gradio as gr
import httpx

DEFAULT_API_BASE_URL = "http://translume-api:8080"
DEFAULT_UI_HOST = "0.0.0.0"
DEFAULT_UI_PORT = 7860


class TranslumeUIConfigError(ValueError):
    """Raised when Gradio UI runtime configuration is invalid."""


@dataclass(frozen=True)
class UIServerConfig:
    """Represent Gradio server launch configuration.

    Attributes:
        host: Host interface for Gradio to bind.
        port: Port for Gradio to listen on.
    """

    host: str
    port: int


def api_base_url_from_environment(
    environment: Mapping[str, str],
) -> str:
    """Return the real FastAPI base URL used by the Gradio UI.

    Acceptance criteria:
        1. Determinism: Same environment returns the same normalized URL.
        2. Validation: Empty URLs raise `TranslumeUIConfigError`.
        3. Validation: URLs must use `http://` or `https://`.
        4. Normalization: Trailing slashes are removed.
        5. No mutation: Environment mapping is not modified.

    Args:
        environment: Environment variable mapping.

    Returns:
        Normalized API base URL.

    Raises:
        TranslumeUIConfigError: If API base URL configuration is invalid.
    """
    raw_value = environment.get("TRANSLUME_API_BASE_URL", DEFAULT_API_BASE_URL)
    value = raw_value.strip().rstrip("/")
    if not value:
        raise TranslumeUIConfigError("TRANSLUME_API_BASE_URL must not be empty")
    if not value.startswith(("http://", "https://")):
        raise TranslumeUIConfigError(
            "TRANSLUME_API_BASE_URL must start with http:// or https://"
        )
    return value


def ui_server_config_from_environment(
    environment: Mapping[str, str],
) -> UIServerConfig:
    """Return Gradio launch configuration from environment variables.

    Acceptance criteria:
        1. Determinism: Same environment returns the same config.
        2. Validation: Empty host raises `TranslumeUIConfigError`.
        3. Validation: Port must be a positive integer.
        4. Defaults: Missing values use Docker-safe defaults.
        5. No mutation: Environment mapping is not modified.

    Args:
        environment: Environment variable mapping.

    Returns:
        UI server configuration.

    Raises:
        TranslumeUIConfigError: If host or port configuration is invalid.
    """
    host = environment.get("TRANSLUME_UI_HOST", DEFAULT_UI_HOST).strip()
    raw_port = environment.get("TRANSLUME_UI_PORT", str(DEFAULT_UI_PORT)).strip()
    if not host:
        raise TranslumeUIConfigError("TRANSLUME_UI_HOST must not be empty")
    try:
        port = int(raw_port)
    except ValueError as error:
        raise TranslumeUIConfigError(
            "TRANSLUME_UI_PORT must be an integer"
        ) from error
    if port <= 0:
        raise TranslumeUIConfigError("TRANSLUME_UI_PORT must be positive")
    return UIServerConfig(host=host, port=port)


def process_pdf(
    file_path: str,
    report_type: str,
) -> tuple[str, str, list[list[str]], object]:
    """Upload a PDF to the API and return packet JSON plus claim cards.

    Acceptance criteria:
        1. Sends the uploaded PDF to FastAPI.
        2. Does not fabricate review content in the UI.
        3. Returns API errors transparently.
        4. Extracts validation-card choices from the API response only.
        5. Uses the configured production API base URL.
    """
    if not file_path:
        return "Upload a PDF first.", "", [], gr.update(choices=[], value=None)
    process_url = f"{api_base_url_from_environment(os.environ)}/api/v1/reports/process"
    with open(file_path, "rb") as handle:
        files = {"file": (file_path, handle, "application/pdf")}
        data = {"report_type": report_type}
        try:
            response = httpx.post(process_url, files=files, data=data, timeout=600)
        except httpx.HTTPError as error:
            return (
                f"API request failed: {error}",
                "",
                [],
                gr.update(choices=[], value=None),
            )
    if response.status_code >= 400:
        return (
            f"API error {response.status_code}: {response.text}",
            "",
            [],
            gr.update(choices=[], value=None),
        )
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
        5. Uses the configured production API base URL.
    """
    if not session_id:
        return (
            "No processed review packet session is available.",
            [],
            gr.update(choices=[], value=None),
        )
    if not claim_id:
        return "Select a claim to validate.", [], gr.update(choices=[], value=None)
    payload = {
        "status": status,
        "reviewer_id": reviewer_id or None,
        "reviewer_note": reviewer_note or None,
    }
    url = (
        f"{api_base_url_from_environment(os.environ)}"
        f"/api/v1/review-packets/{session_id}/claims/{claim_id}/validation"
    )
    try:
        response = httpx.post(url, json=payload, timeout=120)
    except httpx.HTTPError as error:
        return f"API request failed: {error}", [], gr.update(choices=[], value=None)
    if response.status_code >= 400:
        return (
            f"API error {response.status_code}: {response.text}",
            [],
            gr.update(choices=[], value=None),
        )
    data = response.json()
    rows = _claim_rows({"bundle": {"claims": data.get("claims", [])}})
    choices = [row[0] for row in rows]
    return (
        json.dumps(data, indent=2),
        rows,
        gr.update(choices=choices, value=claim_id if claim_id in choices else None),
    )


def fetch_export(session_id: str) -> str:
    """Fetch the persisted review packet export from the API.

    Acceptance criteria:
        1. Requires a stored session ID.
        2. Calls the persisted packet export API endpoint.
        3. Returns only the API response content.
        4. Does not fabricate review-packet data locally.
        5. Uses the configured production API base URL.
    """
    if not session_id:
        return "No processed review packet session is available."
    url = (
        f"{api_base_url_from_environment(os.environ)}"
        f"/api/v1/review-packets/{session_id}/export"
    )
    try:
        response = httpx.get(url, timeout=120)
    except httpx.HTTPError as error:
        return f"API request failed: {error}"
    if response.status_code >= 400:
        return f"API error {response.status_code}: {response.text}"
    return json.dumps(response.json(), indent=2)


def build_app() -> gr.Blocks:
    """Build the Gradio oncologist cockpit.

    Acceptance criteria:
        1. Builds the UI without executing API calls.
        2. Every user action calls the real FastAPI endpoint through handlers.
        3. No static review-packet data is embedded in UI state.
        4. Claim validation controls bind to persisted API actions.
    """
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


def main() -> int:
    """Launch the production Gradio application.

    Acceptance criteria:
        1. Validates the FastAPI base URL before launch.
        2. Uses Docker-safe host and port defaults.
        3. Launches the real Gradio application directly, not through Uvicorn.
        4. Raises a clear configuration error for invalid runtime config.
        5. Does not fabricate UI state before API interaction.

    Returns:
        Process exit code after Gradio stops.
    """
    api_base_url_from_environment(os.environ)
    server_config = ui_server_config_from_environment(os.environ)
    build_app().launch(
        server_name=server_config.host,
        server_port=server_config.port,
    )
    return 0


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
    raise SystemExit(main())
