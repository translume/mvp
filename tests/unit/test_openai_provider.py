from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import BaseModel
from translume_adapters.model_providers.openai_provider import OpenAIModelProvider
from translume_adapters.model_providers.openai_schema import to_openai_strict_schema
from translume_clients.openai_client import OpenAIClient
from translume_core.compiler.decision_brief import (
    DecisionBriefLatencyBudgets,
    _generate_decision_stage_artifact,
)
from translume_core.compiler.structured_model_artifacts import (
    ClaimEvidenceListOutput,
    _BoundedClinicalNarrativeCompilerOutput,
    _BoundedConfirmatoryTestingOutput,
    _BoundedReportExtractionOutput,
    _generate_artifact,
    generate_report_extraction_with_model,
)
from translume_core.provenance.provenance import unique_model_calls
from translume_schemas.decision_brief import (
    ActionableBiologyOutput,
    BiomarkerWatchListOutput,
    CurrentTumorStateOutput,
    NextTestRecommendationsOutput,
    RankedTreatmentOptionsOutput,
    ResistanceForecastOutput,
    RetestingTriggersOutput,
    TranslationalAssessmentOutput,
    TreatmentPressureMapOutput,
)
from translume_schemas.document import DocumentChunk, RetrievedDocumentChunk
from translume_schemas.matrix import TherapyEvidenceMatrixOutput
from translume_schemas.model_calls import (
    ModelAuthenticationError,
    ModelInputBudgetError,
)
from translume_schemas.phenotype import MolecularPhenotypeOutput
from translume_schemas.sankey import MechanismSankeyOutput
from translume_schemas.tumor_behavior import TumorBehaviorModelOutput


class _TinyArtifact(BaseModel):
    artifact_id: str
    value: str


class _ConcurrentArtifact(BaseModel):
    artifact_id: str
    value: str


def _response(value: dict[str, object]) -> dict[str, object]:
    return {
        "id": "resp_real_envelope",
        "status": "completed",
        "model": "gpt-6-astra",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            }
        ],
        "usage": {"input_tokens": 30, "output_tokens": 50, "total_tokens": 80},
    }


def _args():
    return {
        "model_name": "gpt-6-astra",
        "system_prompt": "Use source only",
        "user_prompt": "Source text",
        "schema_name": "_TinyArtifact",
        "json_schema": _TinyArtifact.model_json_schema(),
    }


@pytest.mark.asyncio
async def test_provider_counts_exact_request_and_sends_pro_strict_response():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 30})
        return httpx.Response(
            200, json=_response({"artifact_id": "artifact_1", "value": "ok"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = OpenAIClient("test-key", http_client=http)
        provider = OpenAIModelProvider(client)
        result = await provider.structured_completion(**_args())
    assert result["value"] == "ok"
    count, generation = requests[0][1], requests[1][1]
    assert requests[0][0] == "/v1/responses/input_tokens"
    assert generation["reasoning"] == {"mode": "pro", "effort": "xhigh"}
    assert generation["store"] is False
    assert generation["max_output_tokens"] == 32768
    assert "temperature" not in generation and "messages" not in generation
    assert count == {
        key: value
        for key, value in generation.items()
        if key not in {"store", "max_output_tokens"}
    }
    assert generation["text"]["format"]["strict"] is True
    assert generation["text"]["format"]["schema"]["additionalProperties"] is False
    assert len(provider.call_records) == 2
    assert provider.call_records[-1].wire_schema_hash


@pytest.mark.asyncio
async def test_output_limit_retry_reserves_larger_output_and_keeps_actual_attempts():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 30})
        if body["max_output_tokens"] == 32768:
            return httpx.Response(
                200,
                json={
                    **_response({}),
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            )
        return httpx.Response(
            200, json=_response({"artifact_id": "artifact_1", "value": "ok"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        await provider.structured_completion(**_args())
    assert [
        body["max_output_tokens"]
        for path, body in requests
        if path.endswith("/responses")
    ] == [32768, 65536]
    assert [record.status for record in provider.call_records] == [
        "completed",
        "incomplete",
        "completed",
    ]
    assert len([path for path, body in requests if path.endswith("input_tokens")]) == 1


@pytest.mark.asyncio
async def test_provider_rejects_input_overflow_before_model_generation():
    paths = []

    def handle(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"input_tokens": 100001})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        with pytest.raises(ModelInputBudgetError):
            await provider.structured_completion(**_args())
    assert paths == ["/v1/responses/input_tokens"]


def _write_prompts(tmp_path):
    tmp_path.joinpath("tiny_system.md").write_text(
        "Return a source-backed JSON object."
    )
    tmp_path.joinpath("tiny_user.md").write_text(
        "artifact={planned_artifact_id}\n{payload_json}"
    )


def _generation_kwargs(tmp_path, provider):
    return {
        "prompt_name": "tiny",
        "schema_model": _TinyArtifact,
        "planned_artifact_id": "artifact_expected",
        "payload": {"source": "text"},
        "source_artifact_ids": ["artifact_source"],
        "source_chunk_ids": ["chunk_1"],
        "model_provider": provider,
        "model_name": "gpt-6-astra",
        "prompts_root": tmp_path,
        "created_at": datetime.now(UTC),
    }


@pytest.mark.asyncio
async def test_clinical_repair_never_retries_authentication_failure(tmp_path):
    _write_prompts(tmp_path)
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 30})
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        with pytest.raises(ModelAuthenticationError):
            await _generate_artifact(**_generation_kwargs(tmp_path, provider))
    assert paths == ["/v1/responses/input_tokens", "/v1/responses"]


@pytest.mark.asyncio
async def test_repair_prompt_is_counted_again_and_all_attempts_reach_provenance(
    tmp_path,
):
    _write_prompts(tmp_path)
    generation_count = 0
    counted = []

    def handle(request):
        nonlocal generation_count
        body = json.loads(request.content)
        if request.url.path.endswith("input_tokens"):
            counted.append(body)
            return httpx.Response(200, json={"input_tokens": 30})
        generation_count += 1
        artifact_id = "artifact_wrong" if generation_count == 1 else "artifact_expected"
        return httpx.Response(
            200, json=_response({"artifact_id": artifact_id, "value": "ok"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        result = await _generate_artifact(
            **_generation_kwargs(tmp_path, provider), input_token_budget=100
        )
    assert generation_count == 2
    assert len(counted) == 2
    assert counted[0]["input"] != counted[1]["input"]
    assert "Previous structured-output attempt failed" in counted[1]["input"]
    assert len(result.provenance.model_calls) == 4
    assert result.provenance.provider_name == "openai"
    assert result.provenance.reasoning_mode == "pro"
    assert (
        result.provenance.wire_schema_hash == provider.call_records[-1].wire_schema_hash
    )
    assert len(unique_model_calls([result.provenance, result.provenance])) == 4


@pytest.mark.asyncio
async def test_oversized_repair_is_blocked_before_a_second_generation(tmp_path):
    _write_prompts(tmp_path)
    counts = 0
    generations = 0

    def handle(request):
        nonlocal counts, generations
        if request.url.path.endswith("input_tokens"):
            counts += 1
            return httpx.Response(
                200, json={"input_tokens": 30 if counts == 1 else 101}
            )
        generations += 1
        return httpx.Response(
            200, json=_response({"artifact_id": "wrong", "value": "ok"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        with pytest.raises(ModelInputBudgetError):
            await _generate_artifact(
                **_generation_kwargs(tmp_path, provider), input_token_budget=100
            )
    assert counts == 2
    assert generations == 1


_MAIN_GENERATION_SCHEMAS = [
    _BoundedReportExtractionOutput,
    MolecularPhenotypeOutput,
    TherapyEvidenceMatrixOutput,
    MechanismSankeyOutput,
    _BoundedConfirmatoryTestingOutput,
    TumorBehaviorModelOutput,
    CurrentTumorStateOutput,
    ActionableBiologyOutput,
    RankedTreatmentOptionsOutput,
    TreatmentPressureMapOutput,
    ResistanceForecastOutput,
    BiomarkerWatchListOutput,
    RetestingTriggersOutput,
    NextTestRecommendationsOutput,
    TranslationalAssessmentOutput,
    ClaimEvidenceListOutput,
    _BoundedClinicalNarrativeCompilerOutput,
]


def _require_closed_nodes(node):
    if isinstance(node, list):
        for item in node:
            _require_closed_nodes(item)
    if not isinstance(node, dict):
        return
    if node.get("type") == "object":
        assert node["additionalProperties"] is False
        assert set(node["required"]) == set(node.get("properties", {}))
    for key, value in node.items():
        if key in {"properties", "$defs"}:
            for nested in value.values():
                _require_closed_nodes(nested)
        elif key in {"anyOf", "items"}:
            _require_closed_nodes(value)


@pytest.mark.parametrize("model", _MAIN_GENERATION_SCHEMAS)
def test_every_main_generation_schema_is_strict_without_mutating_public_models(model):
    public = model.model_json_schema()
    original = deepcopy(public)
    wire = to_openai_strict_schema(public)
    _require_closed_nodes(wire)
    assert public == original


def test_schema_normalization_preserves_optional_meaning_and_a_field_named_default():
    schema = {
        "type": "object",
        "properties": {
            "default": {"type": "string", "default": "unused"},
            "optional": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
            },
            "rows": {"type": "array", "items": {"type": "string"}, "default": []},
        },
    }
    wire = to_openai_strict_schema(schema)
    assert set(wire["required"]) == {"default", "optional", "rows"}
    assert wire["properties"]["optional"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert wire["properties"]["rows"]["type"] == "array"
    assert "default" not in wire["properties"]["default"]
    assert schema["properties"]["default"]["default"] == "unused"
    with pytest.raises(ValueError, match="Open-ended"):
        to_openai_strict_schema(
            {"type": "object", "additionalProperties": {"type": "string"}}
        )


@pytest.mark.asyncio
async def test_exact_input_overflow_splits_report_and_retains_every_leaf_trace():
    generated_chunk_ids = []

    def handle(request):
        body = json.loads(request.content)
        prompt = body["input"]
        if "Payload JSON:\n" not in prompt:
            return httpx.Response(200, json={"input_tokens": 10})
        payload = json.loads(prompt.split("Payload JSON:\n", 1)[1])
        chunks = payload["retrieved_chunks"]
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"input_tokens": 101 if len(chunks) > 1 else 30}
            )
        generated_chunk_ids.extend(chunk["chunk_id"] for chunk in chunks)
        return httpx.Response(
            200,
            json=_response(
                {
                    "artifact_id": payload["planned_artifact_id"],
                    "report_type": "NGS",
                    "source_file_id": "source_1",
                    "molecular_findings": [],
                    "negative_findings": [],
                    "assay_limitations": [],
                    "needs_human_review": True,
                }
            ),
        )

    chunks = [
        RetrievedDocumentChunk(
            chunk=DocumentChunk(
                chunk_id=f"chunk_{number}",
                case_id="case_1",
                session_id="session_1",
                source_file_id="source_1",
                report_type="NGS",
                page_start=number,
                page_end=number,
                section="limitations",
                chunk_type="text",
                source_text="Interpretation requires source review.",
                source_block_ids=[f"block_{number}"],
                needs_human_review=True,
            ),
            score=1,
            retrieval_method="lexical",
        )
        for number in (1, 2)
    ]
    from pathlib import Path

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        result = await generate_report_extraction_with_model(
            retrieved_chunks=chunks,
            report_type="NGS",
            source_file_id="source_1",
            model_provider=provider,
            model_name="gpt-6-astra",
            prompts_root=Path("configs/prompts"),
            created_at=datetime.now(UTC),
            input_token_budget=100,
        )
    assert generated_chunk_ids == ["chunk_1", "chunk_2"]
    assert len(result.provenance.component_provenance) == 2
    assert [
        leaf.source_chunk_ids for leaf in result.provenance.component_provenance
    ] == [["chunk_1"], ["chunk_2"]]
    assert len(unique_model_calls([result.provenance])) == len(provider.call_records)
    assert (
        sum(
            call.endpoint == "/responses"
            for call in unique_model_calls([result.provenance])
        )
        == 2
    )


@pytest.mark.asyncio
async def test_decision_stage_keeps_actual_trace_across_timeout_task_boundary(tmp_path):
    _write_prompts(tmp_path)
    stages = []

    def handle(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 30})
        return httpx.Response(
            200, json=_response({"artifact_id": "artifact_expected", "value": "ok"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        result = await _generate_decision_stage_artifact(
            stage_name="current_tumor_state",
            latency_budgets=DecisionBriefLatencyBudgets(default_timeout_seconds=30),
            provenance_sink=stages.append,
            **_generation_kwargs(tmp_path, provider),
        )
    assert stages == [result.provenance]
    assert len(stages[0].model_calls) == 2
    assert stages[0].model_calls[-1].response_id == "resp_real_envelope"


@pytest.mark.asyncio
async def test_concurrent_artifacts_never_claim_peer_calls_or_schema_hashes(tmp_path):
    _write_prompts(tmp_path)
    both_counted = asyncio.Event()
    second_finished = asyncio.Event()
    count_requests = 0

    async def handle(request):
        nonlocal count_requests
        body = json.loads(request.content)
        name = body["text"]["format"]["name"]
        if request.url.path.endswith("input_tokens"):
            count_requests += 1
            if count_requests == 2:
                both_counted.set()
            await both_counted.wait()
            return httpx.Response(200, json={"input_tokens": 30})
        if name == "_TinyArtifact":
            await second_finished.wait()
            artifact_id = "artifact_first"
        else:
            second_finished.set()
            artifact_id = "artifact_second"
        response = _response({"artifact_id": artifact_id, "value": "ok"})
        response["id"] = f"resp_{artifact_id}"
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = OpenAIModelProvider(OpenAIClient("test-key", http_client=http))
        first_kwargs = {
            **_generation_kwargs(tmp_path, provider),
            "planned_artifact_id": "artifact_first",
        }
        second_kwargs = {
            **_generation_kwargs(tmp_path, provider),
            "planned_artifact_id": "artifact_second",
            "schema_model": _ConcurrentArtifact,
        }
        first, second = await asyncio.gather(
            _generate_artifact(**first_kwargs),
            _generate_artifact(**second_kwargs),
        )
    first_calls = first.provenance.model_calls
    second_calls = second.provenance.model_calls
    assert len(first_calls) == len(second_calls) == 2
    assert not (
        {call.call_id for call in first_calls} & {call.call_id for call in second_calls}
    )
    assert first_calls[-1].response_id == "resp_artifact_first"
    assert second_calls[-1].response_id == "resp_artifact_second"
    assert first.provenance.wire_schema_hash != second.provenance.wire_schema_hash
    assert len(unique_model_calls([first.provenance, second.provenance])) == 4
