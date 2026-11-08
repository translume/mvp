"""Contract tests use real PDF parsing and an explicitly mocked HTTP boundary."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import fitz
import httpx
import pytest
from docling_service.main import app as document_app
from docling_service.openai_converter import (
    DocumentConversionError,
    OpenAIDocumentConfig,
    build_page_request,
    convert_pdf_with_openai,
)
from fastapi.testclient import TestClient
from translume_clients.openai_client import OpenAISyncClient
from translume_core.document.quality import score_extraction_quality
from translume_schemas.model_calls import (
    ModelAuthenticationError,
    ModelOutputTruncatedError,
    ModelRefusalError,
)


def _pdf(path: Path) -> None:
    with fitz.open() as document:
        first = document.new_page()
        first.insert_text((60, 60), "MOLECULAR FINDINGS")
        first.insert_text((60, 100), "Unreported EGFR variants were not detected.")
        second = document.new_page()
        second.insert_text((60, 60), "Gene | Value")
        second.insert_text((60, 80), "EGFR | 2.3%")
        document.save(path)


def _response(content: dict, identifier: str = "resp_document_test") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": identifier,
            "status": "completed",
            "model": "gpt-6-astra",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(content)}],
                }
            ],
            "usage": {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
        },
    )


def test_real_pdf_pages_preserve_numbers_native_text_and_call_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input.pdf"
    _pdf(path)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        content = body["input"][0]["content"][0]
        raw = base64.b64decode(content["file_data"].split(",", 1)[1])
        with fitz.open(stream=raw, filetype="pdf") as document:
            assert document.page_count == 1
        if request.url.path.endswith("input_tokens"):
            assert "max_output_tokens" not in body
            return httpx.Response(200, json={"input_tokens": 200})
        if content["filename"] == "page-1.pdf":
            return _response(
                {
                    "blocks": [{"block_type": "heading", "text": "MOLECULAR FINDINGS"}],
                    "tables": [],
                    "warnings": [],
                },
                "resp_page1",
            )
        return _response(
            {
                "blocks": [
                    {"block_type": "table", "text": "Gene | Value\nEGFR | 2.3%"}
                ],
                "tables": [{"rows": [["Gene", "Value"], ["EGFR", "2.3%"]]}],
                "warnings": [],
            },
            "resp_page2",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = OpenAISyncClient(
            "unit-test-key", http_client=http, correlation_id="file_test"
        )
        result = convert_pdf_with_openai(
            path, source_file_id="file_test", client=client
        )
    assert result.extraction_method == "openai"
    assert [page.page_number for page in result.pages] == [1, 2]
    assert "not detected" in result.pages[0].text
    assert result.pages[0].blocks[0].bbox is None
    native = [
        block for block in result.pages[0].blocks if block.block_type == "native_text"
    ]
    assert native and native[0].bbox is not None
    assert all(
        block.confidence is None for page in result.pages for block in page.blocks
    )
    assert result.pages[1].tables[0].rows[1] == ["EGFR", "2.3%"]
    assert result.needs_human_review is True
    # Call receipts and retained native text are not extraction-quality defects.
    assert score_extraction_quality(result).quality_score == 1.0
    assert len(result.model_calls) == 4
    assert {record.correlation_id for record in result.model_calls} == {"file_test"}
    for endpoint, body in requests:
        assert body["model"] == "gpt-6-astra"
        assert body["reasoning"]["mode"] == "pro"
        assert "temperature" not in body
        if endpoint == "/v1/responses":
            assert body["store"] is False


@pytest.mark.parametrize("failure", ["auth", "refusal"])
def test_pdf_provider_failure_never_returns_partial_extraction(
    tmp_path: Path, failure: str
) -> None:
    path = tmp_path / "input.pdf"
    _pdf(path)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        if failure == "auth":
            return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
        return httpx.Response(
            200,
            json={
                "id": "resp_refusal",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "refused"}],
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = OpenAISyncClient("unit-test-key", http_client=http)
        expected = ModelAuthenticationError if failure == "auth" else ModelRefusalError
        with pytest.raises(expected):
            convert_pdf_with_openai(path, source_file_id="file_test", client=client)
    assert calls == ["/v1/responses/input_tokens", "/v1/responses"]


def test_pdf_input_budget_checks_complete_request_before_inference(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input.pdf"
    _pdf(path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("input_tokens")
        assert json.loads(request.content)["text"]["format"]["strict"] is True
        return httpx.Response(200, json={"input_tokens": 100001})

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(DocumentConversionError, match="input-token budget"),
    ):
        convert_pdf_with_openai(
            path,
            source_file_id="file_test",
            client=OpenAISyncClient("unit-test-key", http_client=http),
        )


@pytest.mark.parametrize("retry_succeeds", [True, False])
def test_pdf_output_limit_gets_one_counted_retry_without_using_partial_output(
    tmp_path: Path, retry_succeeds: bool
) -> None:
    path = tmp_path / "one-page.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((60, 60), "EGFR 2.3%")
        document.save(path)
    requests: list[tuple[str, dict]] = []
    generation_requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 200})
        generation_requests.append(body)
        if len(generation_requests) == 1 or not retry_succeeds:
            return httpx.Response(
                200,
                json={
                    "id": f"resp_truncated_{len(generation_requests)}",
                    "model": "gpt-6-astra",
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "{unusable-partial-text",
                                }
                            ],
                        }
                    ],
                },
            )
        return _response(
            {
                "blocks": [{"block_type": "text", "text": "EGFR 2.3%"}],
                "tables": [],
                "warnings": [],
            }
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = OpenAISyncClient("unit-test-key", http_client=http)
        if retry_succeeds:
            result = convert_pdf_with_openai(
                path, source_file_id="file_test", client=client
            )
            assert result.pages[0].text == "EGFR 2.3%"
        else:
            with pytest.raises(ModelOutputTruncatedError):
                convert_pdf_with_openai(path, source_file_id="file_test", client=client)
        records = [
            record for record in client.call_records if record.endpoint == "/responses"
        ]
    assert [body["max_output_tokens"] for body in generation_requests] == [32768, 65536]
    assert generation_requests[0]["input"] == generation_requests[1]["input"]
    assert "unusable-partial-text" not in json.dumps(generation_requests)
    assert [path for path, _ in requests] == [
        "/v1/responses/input_tokens",
        "/v1/responses",
        "/v1/responses/input_tokens",
        "/v1/responses",
    ]
    assert [record.status for record in records] == [
        "incomplete",
        "completed" if retry_succeeds else "incomplete",
    ]


def test_page_request_rejects_size_limit_and_invalid_routing() -> None:
    config = OpenAIDocumentConfig(max_page_bytes=4)
    with pytest.raises(DocumentConversionError, match="upload limit"):
        build_page_request(b"large", page_number=1, config=config)
    with pytest.raises(ValueError, match="pro"):
        OpenAIDocumentConfig(reasoning_mode="standard")


def test_document_http_upload_runs_real_pdf_conversion_and_returns_audit_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.pdf"
    _pdf(path)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    journal = tmp_path / "document-calls.jsonl"
    monkeypatch.setenv("OPENAI_AUDIT_PATH", str(journal))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["input"][0]["content"][0]["detail"] == "high"
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 200})
        return _response({"blocks": [], "tables": [], "warnings": []})

    with (
        TestClient(document_app) as service,
        httpx.Client(transport=httpx.MockTransport(handler)) as model_http,
    ):
        document_app.state.openai_http = model_http
        result = service.post(
            "/extract",
            files={"file": ("input.pdf", path.read_bytes(), "application/pdf")},
            data={"source_file_id": "file_http_test", "extraction_method": "openai"},
        )
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["source_file_id"] == "file_http_test"
        assert len(payload["pages"]) == 2
        assert "not detected" in payload["pages"][0]["text"]
        assert len(payload["model_calls"]) == 4
        assert service.get("/health").json()["local_inference_enabled"] is False
        rejected = service.post(
            "/extract", files={"file": ("wrong.pdf", b"invalid", "application/pdf")}
        )
        assert rejected.status_code == 415
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert len(records) == 4
    assert all(record["correlation_id"] == "file_http_test" for record in records)
    assert "unit-test-key" not in journal.read_text()
