from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from docling_service.converter import DoclingServiceError, convert_pdf_with_docling

app = FastAPI(title="docling_service")


@app.get("/health")
def health() -> dict[str, object]:
    """Return service health and dependency availability."""
    try:
        import docling  # noqa: F401
        docling_available = True
    except ImportError:
        docling_available = False
    return {
        "status": "ok",
        "service": "docling_service",
        "docling_available": docling_available,
    }


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    source_file_id: str = Form(""),
    extraction_method: str = Form("docling"),
) -> dict[str, object]:
    """Convert an uploaded PDF into Translume document extraction JSON.

    Acceptance criteria:
        1. Accepts one PDF upload.
        2. Runs real Docling conversion.
        3. Returns DocumentExtractionOutput JSON.
        4. Does not produce clinical findings or clinical reasoning.
        5. Dependency or conversion failures return explicit errors.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    resolved_source_file_id = source_file_id.strip() or _source_file_id(content)
    suffix = Path(file.filename or "uploaded.pdf").suffix or ".pdf"
    with tempfile.TemporaryDirectory(prefix="translume_docling_") as temp_dir:
        pdf_path = Path(temp_dir) / f"{resolved_source_file_id}{suffix}"
        pdf_path.write_bytes(content)
        try:
            output = convert_pdf_with_docling(
                pdf_path,
                source_file_id=resolved_source_file_id,
                extraction_method=extraction_method,
            )
        except (DoclingServiceError, FileNotFoundError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return output.model_dump(mode="json")


def _source_file_id(content: bytes) -> str:
    return f"file_{hashlib.sha256(content).hexdigest()[:16]}"
