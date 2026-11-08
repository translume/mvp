"""Internal CPU service for bounded, remote OpenAI PDF transcription."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from translume_clients.openai_client import OpenAISyncClient
from translume_ports.model_provider import ModelProviderError

from docling_service.openai_converter import (
    DocumentConversionError,
    convert_pdf_with_openai,
    document_config_from_environment,
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Own the pooled API client and bounded document-conversion concurrency."""
    config = document_config_from_environment()
    pool = httpx.Client(follow_redirects=False)
    OpenAISyncClient(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=float(os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", "900")),
        http_client=pool,
    )
    application.state.openai_http = pool
    application.state.document_config = config
    application.state.conversion_semaphore = asyncio.Semaphore(2)
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="translume_remote_document_service", lifespan=lifespan)


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    """Report local readiness without claiming that a live API call succeeded."""
    configured = hasattr(request.app.state, "openai_http")
    config = getattr(request.app.state, "document_config", None)
    return {
        "status": "ok" if configured else "unconfigured",
        "service": "docling_service",
        "provider": "openai",
        "remote_model_configured": configured,
        "document_model": config.model_name if config else None,
        "reasoning_mode": config.reasoning_mode if config else None,
        "local_inference_enabled": False,
    }


@app.post("/extract")
async def extract(
    request: Request,
    file: Annotated[UploadFile, File()],
    source_file_id: Annotated[str, Form()] = "",
    extraction_method: Annotated[str, Form()] = "openai",
) -> dict[str, object]:
    """Transcribe an uploaded PDF through OpenAI without blocking health checks.

    Acceptance criteria:
        1. Stream uploads to a bounded temporary file with no user-derived path.
        2. Reject empty, oversized or non-PDF content before model inference.
        3. Preserve provider failures as failures, never successful empty output.
        4. Remove temporary source bytes after success or failure.
    """
    if extraction_method != "openai":
        raise HTTPException(status_code=400, detail="extraction_method must be openai")
    max_bytes = request.app.state.document_config.max_upload_bytes
    with tempfile.TemporaryDirectory(prefix="translume_document_") as directory:
        path = Path(directory) / "source.pdf"
        digest = hashlib.sha256()
        total = 0
        prefix = b""
        with path.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413, detail="PDF upload exceeds size limit"
                    )
                if not prefix:
                    prefix = chunk[:1024]
                digest.update(chunk)
                stream.write(chunk)
        if not total:
            raise HTTPException(status_code=400, detail="uploaded file is empty")
        if b"%PDF-" not in prefix:
            raise HTTPException(status_code=415, detail="uploaded file must be a PDF")
        resolved_id = source_file_id.strip() or f"file_{digest.hexdigest()[:16]}"
        try:
            async with request.app.state.conversion_semaphore:
                with OpenAISyncClient(
                    api_key=os.environ.get("OPENAI_API_KEY", ""),
                    base_url=os.environ.get(
                        "OPENAI_BASE_URL", "https://api.openai.com/v1"
                    ),
                    timeout_seconds=float(
                        os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", "900")
                    ),
                    http_client=request.app.state.openai_http,
                    audit_path=os.environ.get("OPENAI_AUDIT_PATH") or None,
                    correlation_id=resolved_id,
                ) as client:
                    output = await asyncio.to_thread(
                        convert_pdf_with_openai,
                        path,
                        source_file_id=resolved_id,
                        extraction_method="openai",
                        client=client,
                        config=request.app.state.document_config,
                    )
        except ModelProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except (DocumentConversionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return output.model_dump(mode="json")
