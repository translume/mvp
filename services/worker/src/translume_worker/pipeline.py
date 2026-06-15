from __future__ import annotations

from pathlib import Path

from translume_core.workflow import (
    TranslumeWorkflowConfig,
    TranslumeWorkflowProviders,
    process_report_pdf,
)


async def process_pdf_path(
    path: Path,
    report_type: str,
    config: TranslumeWorkflowConfig,
    providers: TranslumeWorkflowProviders,
):
    """Process a PDF path through the same production workflow as the API.

    Acceptance criteria:
        1. Reads bytes from a caller-supplied file path.
        2. Delegates all domain behavior to `process_report_pdf`.
        3. Does not use mocks or sample payloads.
    """
    return await process_report_pdf(
        filename=path.name,
        content=path.read_bytes(),
        report_type=report_type,
        config=config,
        providers=providers,
    )
