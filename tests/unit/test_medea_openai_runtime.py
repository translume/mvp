"""Real upstream Medea contracts with explicitly mocked remote HTTP responses."""

from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
from threading import Event

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from medea_service.database_runtime import (
    MedeaDatabaseError,
    _close_lookup,
    _open_depmap_lookup,
    depmap_correlation,
    inspect_medeadb,
    validate_medeadb_runtime,
)
from medea_service.literature_search import (
    LiteratureSourceError,
    PublicLiteratureSearch,
    search_queries,
)
from medea_service.main import app
from medea_service.openai_literature_action import run_literature_pipeline
from medea_service.openai_reranker import OpenAIEmbeddingReranker, _segment_utf8
from medea_service.openai_runtime import (
    OpenAICompletion,
    OpenAIMedeaConfig,
    build_openai_medea_config,
)
from medea_service.vendor_runtime import VendorRuntimeError, import_vendor_module
from translume_adapters.embedding_providers.openai_embedding_provider import (
    OpenAISyncEmbeddingProvider,
)
from translume_clients.openai_client import OpenAISyncClient
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.model_calls import (
    ModelAuthenticationError,
    ModelOutputTruncatedError,
)

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "third_party" / "upstream" / "Medea"


def _context() -> EvidenceContextBundle:
    return EvidenceContextBundle(
        artifact_id="artifact_test_context",
        extraction=ReportExtractionOutput(
            artifact_id="artifact_test_extraction",
            report_type="NGS",
            disease="sarcoma",
            source_file_id="file_test",
            molecular_findings=[
                MolecularFinding(
                    finding_id="finding_test_mtap",
                    gene="MTAP",
                    alteration="loss",
                    alteration_type="copy_number_loss",
                    confidence=0.9,
                ),
                MolecularFinding(
                    finding_id="finding_test_cdkn2a",
                    gene="CDKN2A",
                    alteration="loss",
                    alteration_type="copy_number_loss",
                    confidence=0.9,
                ),
            ],
        ),
        graph_evidence=GraphEvidenceArtifact(
            artifact_id="artifact_test_graph", source_entity_ids=[], nodes=[], edges=[]
        ),
        tool_outputs=[],
        medea_reasoning=MedeaReasoningArtifact(
            artifact_id="artifact_not_yet_run",
            reasoning_mode="not_yet_run",
            summary="",
            supported_hypotheses=[],
            weakened_hypotheses=[],
        ),
    )


def _database(tmp_path: Path) -> Path:
    root = tmp_path / "MedeaDB"
    data = root / "depmap_24q2"
    data.mkdir(parents=True)
    names = np.array(["MTAP", "CDKN2A", "PRMT5"])
    np.save(data / "gene_idx_array.npy", names)
    (data / "gene_names.txt").write_text("MTAP\nCDKN2A\nPRMT5\n")
    np.save(
        data / "corr_matrix.npy",
        np.array([[1.0, 0.75, 0.8], [0.75, 1.0, 0.2], [0.8, 0.2, 1.0]]),
    )
    np.save(
        data / "p_val_matrix.npy",
        np.array([[0.0, 0.001, 0.0001], [0.001, 0.0, 0.2], [0.0001, 0.2, 0.0]]),
    )
    np.save(
        data / "p_adj_matrix.npy",
        np.array([[0.0, 0.01, 0.001], [0.01, 0.0, 0.4], [0.001, 0.4, 0.0]]),
    )
    return root


def _literature_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "www.ebi.ac.uk":
        return httpx.Response(
            200,
            json={
                "hitCount": 1,
                "resultList": {
                    "result": [
                        {
                            "id": "12345",
                            "source": "MED",
                            "title": "Synthetic test fixture study",
                            "abstractText": "<p>MTAP loss was studied in laboratory cells.</p>",
                            "pubYear": "2020",
                            "citedByCount": 2,
                        }
                    ]
                },
            },
        )
    return httpx.Response(200, json={"total": 0, "data": []})


def _response(text: str, number: int) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-request-id": f"req_test_{number}"},
        json={
            "id": f"resp_test_{number}",
            "status": "completed",
            "model": "gpt-6-astra",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": text}]}
            ],
            "usage": {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
        },
    )


class _ModelHTTP:
    def __init__(self, *, reject_auth: bool = False, wrong_ids: bool = False):
        self.requests: list[dict] = []
        self.paths: list[str] = []
        self.reject_auth = reject_auth
        self.wrong_ids = wrong_ids

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openai.com"
        body = json.loads(request.content)
        self.requests.append(body)
        self.paths.append(request.url.path)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        if self.reject_auth:
            return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})
        if request.url.path.endswith("embeddings"):
            return httpx.Response(
                200,
                json={
                    "model": "text-embedding-3-large",
                    "data": [
                        {"index": index, "embedding": [1.0, 0.25 + index / 100.0]}
                        for index in reversed(range(len(body["input"])))
                    ],
                    "usage": {"prompt_tokens": 10, "total_tokens": 10},
                },
            )
        schema = body.get("text", {}).get("format", {}).get("name")
        if schema == "MedeaPaperJudgements":
            result = {
                "judgements": [
                    {
                        "source_id": "invented" if self.wrong_ids else "epmc:MED:12345",
                        "relevant": True,
                        "reason": "Laboratory mechanism relates to the question.",
                    }
                ]
            }
            return _response(json.dumps(result), len(self.paths))
        if schema == "MedeaCitedSynthesis":
            result = {
                "summary": "The retrieved laboratory abstract studies MTAP loss [0].",
                "supported_hypotheses": ["MTAP loss warrants mechanistic review [0]."],
                "weakened_hypotheses": [],
                "cited_indices": [0],
                "limitations": [
                    "Abstract-only laboratory evidence requires human review."
                ],
            }
            return _response(json.dumps(result), len(self.paths))
        return _response(
            "The retrieved abstract studies MTAP loss [0].", len(self.paths)
        )


def test_openai_config_preserves_key_and_rejects_local_or_alternate_routes() -> None:
    environment = {"OPENAI_API_KEY": "unit-test-key", "OPENAI_REASONING_MODE": "pro"}
    config = build_openai_medea_config(environment)
    assert config.api_key == "unit-test-key"
    assert "unit-test-key" not in repr(config)
    assert environment == {
        "OPENAI_API_KEY": "unit-test-key",
        "OPENAI_REASONING_MODE": "pro",
    }
    with pytest.raises(VendorRuntimeError, match="api.openai.com"):
        build_openai_medea_config(
            {**environment, "OPENAI_BASE_URL": "http://localhost:8000/v1"}
        )
    with pytest.raises(VendorRuntimeError, match="only OpenAI"):
        build_openai_medea_config(
            {**environment, "ANTHROPIC_API_KEY": "another-test-key"}
        )
    with pytest.raises(VendorRuntimeError, match="Astra"):
        build_openai_medea_config(
            {**environment, "OPENAI_REASONING_MODEL": "local-model"}
        )


def test_actual_upstream_modules_import_without_any_local_model_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__
    forbidden = {
        "torch",
        "transformers",
        "FlagEmbedding",
        "sentence_transformers",
        "medea",
        "ollama",
        "anthropic",
    }

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"forbidden local/provider dependency import: {name}")
        return real_import(name, *args, **kwargs)

    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (VENDOR / "medea/tool_space").glob("*.py")
    }
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    runtime = import_vendor_module(VENDOR, ("medea",))
    module = runtime.new_open_scholar_module()
    assert module.OpenScholar.__module__ == "medea_service.vendor_modules.open_scholar"
    assert runtime.depmap_module.GeneCorrelationLookup.__module__.endswith(".depmap")
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (VENDOR / "medea/tool_space").glob("*.py")
    }
    assert before == after


def test_real_depmap_parser_reads_memory_mapped_arrays_without_checkpoints(
    tmp_path: Path,
) -> None:
    root = _database(tmp_path)
    source = import_vendor_module(VENDOR, ("medea",))
    status = inspect_medeadb(root)
    assert status.available is True
    assert status.resources == {"depmap_24q2": True}
    assert status.as_dict()["profile"] == "depmap_24q2"
    validation = validate_medeadb_runtime(source, status)
    assert validation.gene_count == 3
    lookup = _open_depmap_lookup(source, status)
    try:
        assert isinstance(lookup.corr_matrix, np.memmap)
        assert isinstance(lookup.p_val_matrix, np.memmap)
    finally:
        _close_lookup(lookup)
    result = depmap_correlation(source, status, "mtap", "cdkn2a")
    assert result.correlation == 0.75
    assert result.p_value == 0.001
    assert result.adjusted_p_value == 0.01


def test_depmap_startup_rejects_mismatched_matrix_shape(tmp_path: Path) -> None:
    root = _database(tmp_path)
    np.save(root / "depmap_24q2/p_val_matrix.npy", np.zeros((2, 2)))
    with pytest.raises(MedeaDatabaseError, match="does not match the gene index"):
        validate_medeadb_runtime(
            import_vendor_module(VENDOR, ("medea",)), inspect_medeadb(root)
        )


def test_depmap_nonfinite_observation_cannot_become_scientific_evidence(
    tmp_path: Path,
) -> None:
    root = _database(tmp_path)
    path = root / "depmap_24q2/corr_matrix.npy"
    matrix = np.load(path)
    matrix[0, 1] = float("nan")
    np.save(path, matrix)
    with pytest.raises(MedeaDatabaseError, match="nonfinite"):
        depmap_correlation(
            import_vendor_module(VENDOR, ("medea",)),
            inspect_medeadb(root),
            "MTAP",
            "CDKN2A",
        )


def test_actual_upstream_openscholar_search_judge_rank_and_synthesize_use_openai() -> (
    None
):
    model = _ModelHTTP()
    with (
        httpx.Client(transport=httpx.MockTransport(model)) as model_http,
        httpx.Client(transport=httpx.MockTransport(_literature_handler)) as data_http,
    ):
        client = OpenAISyncClient("unit-test-key", http_client=model_http)
        completion = OpenAICompletion(
            client, OpenAIMedeaConfig("unit-test-key", embedding_dimensions=2)
        )
        result = run_literature_pipeline(
            runtime=import_vendor_module(VENDOR, ("medea",)),
            search=PublicLiteratureSearch(data_http),
            queries=search_queries("sarcoma", ("MTAP",)),
            question="Evaluate MTAP loss as laboratory evidence, with uncertainty.",
            completion=completion,
        )
    assert result.status == "succeeded"
    assert result.references[0].source_id == "epmc:MED:12345"
    assert result.references[0].pmid == "12345"
    assert len(result.judgements) == 1
    assert len(result.search_result.searches) == 2
    assert "/v1/embeddings" in model.paths
    assert model.paths.count("/v1/responses") == 3
    assert model.paths.count("/v1/responses/input_tokens") == 3
    for path, body in zip(model.paths, model.requests, strict=True):
        if "responses" in path:
            assert body["reasoning"]["mode"] == "pro"
            assert body["model"] == "gpt-6-astra"
            assert "temperature" not in body and "seed" not in body
        if path == "/v1/responses":
            assert body["store"] is False


def test_both_actual_openscholar_ranking_methods_use_remote_embeddings() -> None:
    model = _ModelHTTP()
    with httpx.Client(transport=httpx.MockTransport(model)) as http:
        client = OpenAISyncClient("unit-test-key", http_client=http)
        embedding = OpenAISyncEmbeddingProvider(client, dimensions=2)
        module = import_vendor_module(VENDOR, ("medea",)).new_open_scholar_module()
        scholar = module.OpenScholar(
            None,
            None,
            client_llm="gpt-6-astra",
            reranker=OpenAIEmbeddingReranker(embedding),
        )
        original = {
            "input": "MTAP mechanism",
            "ctxs": [{"title": "A", "text": "First real passage contract"}],
        }
        first, scores, mapping = scholar.reranking_passages_cross_encoder(original)
        second, more_scores, _ = scholar.reranking_passages_cross_encoder_supplemental(
            original, [{"title": "B", "text": "Supplemental passage contract"}]
        )
    assert first and second and scores and more_scores
    assert mapping == {0: 0}
    assert model.paths.count("/v1/embeddings") == 2


def test_long_multibyte_passages_are_fully_segmented_before_remote_embedding() -> None:
    text = "基因" * 5000 + " EGFR 2.3%"
    parts = _segment_utf8(text)
    assert "".join(parts) == text
    assert all(len(part.encode()) <= 8000 for part in parts)
    model = _ModelHTTP()
    with httpx.Client(transport=httpx.MockTransport(model)) as http:
        provider = OpenAISyncEmbeddingProvider(
            OpenAISyncClient("unit-test-key", http_client=http), dimensions=2
        )
        scores = OpenAIEmbeddingReranker(provider).compute_score(
            [[text, text], ["short query", text]]
        )
    assert len(scores) == 2
    assert scores[0] == pytest.approx(1.0)
    embedded = [value for body in model.requests for value in body.get("input", [])]
    assert all(
        isinstance(value, str) and len(value.encode()) <= 8000 for value in embedded
    )


def test_auth_error_never_becomes_negative_literature_evidence() -> None:
    model = _ModelHTTP(reject_auth=True)
    with (
        httpx.Client(transport=httpx.MockTransport(model)) as http,
        httpx.Client(transport=httpx.MockTransport(_literature_handler)) as data,
    ):
        completion = OpenAICompletion(
            OpenAISyncClient("unit-test-key", http_client=http),
            OpenAIMedeaConfig("unit-test-key", embedding_dimensions=2),
        )
        with pytest.raises(ModelAuthenticationError):
            run_literature_pipeline(
                runtime=import_vendor_module(VENDOR, ("medea",)),
                search=PublicLiteratureSearch(data),
                queries=("MTAP",),
                question="MTAP mechanism",
                completion=completion,
            )
    assert model.paths.count("/v1/responses") == 1
    assert "/v1/embeddings" not in model.paths


def test_missing_or_invented_judgement_id_fails_instead_of_dropping_paper() -> None:
    model = _ModelHTTP(wrong_ids=True)
    with (
        httpx.Client(transport=httpx.MockTransport(model)) as http,
        httpx.Client(transport=httpx.MockTransport(_literature_handler)) as data,
    ):
        completion = OpenAICompletion(
            OpenAISyncClient("unit-test-key", http_client=http),
            OpenAIMedeaConfig("unit-test-key", embedding_dimensions=2),
        )
        with pytest.raises(VendorRuntimeError, match="source IDs"):
            run_literature_pipeline(
                runtime=import_vendor_module(VENDOR, ("medea",)),
                search=PublicLiteratureSearch(data),
                queries=("MTAP",),
                question="MTAP mechanism",
                completion=completion,
            )


def test_genuine_empty_search_is_distinct_from_source_failure() -> None:
    def empty(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(
                200, json={"hitCount": 0, "resultList": {"result": []}}
            )
        return httpx.Response(200, json={"total": 0, "data": []})

    model = _ModelHTTP()
    with (
        httpx.Client(transport=httpx.MockTransport(model)) as http,
        httpx.Client(transport=httpx.MockTransport(empty)) as data,
    ):
        result = run_literature_pipeline(
            runtime=import_vendor_module(VENDOR, ("medea",)),
            search=PublicLiteratureSearch(data),
            queries=("MTAP",),
            question="MTAP mechanism",
            completion=OpenAICompletion(
                OpenAISyncClient("unit-test-key", http_client=http),
                OpenAIMedeaConfig("unit-test-key"),
            ),
        )
    assert result.status == "no_retrieved_abstracts"
    assert "does not establish absence" in result.summary
    assert not model.requests
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(403))
        ) as data,
        pytest.raises(LiteratureSourceError, match="all_sources_unavailable"),
    ):
        PublicLiteratureSearch(data).search(("MTAP",))


def test_cancelled_completion_never_sends_a_followup_request() -> None:
    cancelled = Event()
    cancelled.set()
    model = _ModelHTTP()
    with httpx.Client(transport=httpx.MockTransport(model)) as http:
        completion = OpenAICompletion(
            OpenAISyncClient("unit-test-key", http_client=http),
            OpenAIMedeaConfig("unit-test-key"),
            cancelled,
        )
        with pytest.raises(VendorRuntimeError, match="cancelled"):
            completion("Do not send this cancelled request")
    assert not model.requests


@pytest.mark.parametrize("retry_succeeds", [True, False])
def test_medea_output_limit_gets_one_bounded_retry_and_preserves_attempt_receipts(
    retry_succeeds: bool,
) -> None:
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
                                    "text": "unusable-partial-claim",
                                }
                            ],
                        }
                    ],
                },
            )
        return _response("Completed source-bound synthesis.", 2)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = OpenAISyncClient("unit-test-key", http_client=http)
        completion = OpenAICompletion(client, OpenAIMedeaConfig("unit-test-key"))
        if retry_succeeds:
            assert (
                completion("Source-bound synthesis")
                == "Completed source-bound synthesis."
            )
            assert completion.response_ids == ("resp_test_2",)
        else:
            with pytest.raises(ModelOutputTruncatedError):
                completion("Source-bound synthesis")
            assert completion.response_ids == ()
        records = [
            record for record in client.call_records if record.endpoint == "/responses"
        ]
    assert [body["max_output_tokens"] for body in generation_requests] == [32768, 65536]
    assert generation_requests[0]["input"] == generation_requests[1]["input"]
    assert "unusable-partial-claim" not in json.dumps(generation_requests)
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


def test_service_keeps_real_database_citations_call_journal_and_failure_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This test injects MockTransport into both pools before the first request;
    # it must not depend on the test host's optional proxy client packages.
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    database = _database(tmp_path)
    journal = tmp_path / "calls.jsonl"
    monkeypatch.setenv("MEDEA_VENDOR_DIR", str(VENDOR))
    monkeypatch.setenv("MEDEADB_PATH", str(database))
    monkeypatch.setenv("MEDEA_REQUIRE_DATABASE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "2")
    monkeypatch.setenv("OPENAI_AUDIT_PATH", str(journal))
    model = _ModelHTTP()
    with TestClient(app) as test_client:
        runtime = app.state.runtime
        with (
            httpx.Client(transport=httpx.MockTransport(model)) as http,
            httpx.Client(transport=httpx.MockTransport(_literature_handler)) as data,
        ):
            from dataclasses import replace

            app.state.runtime = replace(runtime, model_http=http, literature_http=data)
            contract = test_client.get("/runtime-contract").json()
            assert contract["database_parseable"] is True
            assert contract["local_inference_enabled"] is False
            assert contract["remote_api_verified"] is False
            response = test_client.post(
                "/reason", json={"context": _context().model_dump(mode="json")}
            )
            assert response.status_code == 200, response.text
            artifact = MedeaReasoningArtifact.model_validate(response.json())
            assert artifact.model_reasoning_mode == "pro"
            assert "MTAP/CDKN2A: r=0.7500" in artifact.summary
            assert artifact.source_references[0].pmid == "12345"
            assert artifact.model_calls
            assert all(
                call.correlation_id == "artifact_test_context"
                for call in artifact.model_calls
            )
            persisted = [json.loads(line) for line in journal.read_text().splitlines()]
            assert len(persisted) == len(artifact.model_calls)
            assert "unit-test-key" not in journal.read_text()
            assert "Synthetic test fixture" not in journal.read_text()
            model.reject_auth = True
            failed = test_client.post(
                "/reason", json={"context": _context().model_dump(mode="json")}
            )
            assert failed.status_code == 502
            assert "API key" in failed.json()["detail"]
