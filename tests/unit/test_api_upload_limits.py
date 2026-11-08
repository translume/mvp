from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from translume_api.main import _read_pdf_upload


@pytest.mark.asyncio
async def test_pdf_upload_preserves_source_bytes():
    content = b"%PDF-1.7\nactual source bytes"
    assert await _read_pdf_upload(UploadFile(BytesIO(content)), max_bytes=64) == content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content,limit,status",
    [(b"", 10, 400), (b"not a pdf", 32, 415), (b"%PDF-" + b"x" * 20, 10, 413)],
)
async def test_invalid_upload_is_rejected_before_inference(content, limit, status):
    upload = UploadFile(BytesIO(content))
    with pytest.raises(HTTPException) as error:
        await _read_pdf_upload(upload, max_bytes=limit)
    assert error.value.status_code == status
    assert upload.file.tell() <= limit + 1
