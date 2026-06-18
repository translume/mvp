from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from optimuskg_service.main import context as optimuskg_context
from optimuskg_service.main import ContextRequest
from tooluniverse_service.main import workflows as tooluniverse_workflows
from tooluniverse_service.main import WorkflowRequest
from medea_service.main import reason as medea_reason
from medea_service.main import runtime_contract as medea_runtime_contract
from medea_service.main import ReasonRequest
from translume_schemas.entities import NormalizedEntity, NormalizedEntitySet
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact


def _write_fake_optimuskg_repo(tmp_path: Path):
    """Create a tiny real OptimusKG-shaped package with parquet graph data."""
    import json
    pl = pytest.importorskip("polars")

    repo = tmp_path / "OptimusKG"
    package_dir = repo / "packages" / "optimuskg" / "src" / "optimuskg"
    package_dir.mkdir(parents=True)
    cache_dir = tmp_path / "optimuskg_cache"
    cache_dir.mkdir()
    nodes_path = cache_dir / "largest_connected_component_nodes.parquet"
    edges_path = cache_dir / "largest_connected_component_edges.parquet"
    pl.DataFrame(
        [
            {
                "id": "GENE:CHEK2",
                "label": "gene",
                "properties": json.dumps({"name": "CHEK2", "synonyms": ["CHEK2"]}),
            },
            {
                "id": "GENE:MTAP",
                "label": "gene",
                "properties": json.dumps({"name": "MTAP", "synonyms": ["MTAP"]}),
            },
            {
                "id": "PATHWAY:DNA_DAMAGE_RESPONSE",
                "label": "pathway",
                "properties": json.dumps({"name": "DNA damage response"}),
            },
            {
                "id": "PATHWAY:METHYLATION_CONTEXT",
                "label": "pathway",
                "properties": json.dumps({"name": "Methylation context"}),
            },
        ]
    ).write_parquet(nodes_path)
    pl.DataFrame(
        [
            {
                "from": "GENE:CHEK2",
                "to": "PATHWAY:DNA_DAMAGE_RESPONSE",
                "label": "participates_in",
                "relation": "biolink:participates_in",
                "undirected": False,
                "properties": json.dumps({"source": "fixture_optimuskg_parquet"}),
            },
            {
                "from": "GENE:MTAP",
                "to": "PATHWAY:METHYLATION_CONTEXT",
                "label": "associated_with",
                "relation": "biolink:associated_with",
                "undirected": False,
                "properties": json.dumps({"source": "fixture_optimuskg_parquet"}),
            },
        ]
    ).write_parquet(edges_path)
    (package_dir / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"_CACHE_DIR = Path({str(cache_dir)!r})\n"
        "def set_cache_dir(path):\n"
        "    global _CACHE_DIR\n"
        "    _CACHE_DIR = Path(path)\n"
        "def get_file(relative_path, force=False):\n"
        "    path = _CACHE_DIR / relative_path\n"
        "    if not path.exists():\n"
        "        raise FileNotFoundError(path)\n"
        "    return path\n",
        encoding="utf-8",
    )
    return repo, cache_dir


def _entities() -> NormalizedEntitySet:
    return NormalizedEntitySet(
        artifact_id="artifact_entities",
        case_id="case_1",
        session_id="session_1",
        entities=[
            NormalizedEntity(
                entity_id="entity_gene",
                entity_type="gene",
                original_text="MTAP",
                normalized_label="MTAP",
                source_artifact_id="artifact_report",
            ),
            NormalizedEntity(
                entity_id="entity_disease",
                entity_type="disease",
                original_text="dedifferentiated chondrosarcoma",
                normalized_label="dedifferentiated chondrosarcoma",
                source_artifact_id="artifact_report",
            ),
        ],
    )


def _write_package(root: Path, package: str, files: dict[str, str]) -> None:
    package_dir = root / package
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text(files.get("__init__.py", ""), encoding="utf-8")
    for name, text in files.items():
        if name == "__init__.py":
            continue
        path = package_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.mark.asyncio
async def test_optimuskg_service_uses_real_client_and_parquet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "optimuskg", raising=False)
    repo, cache_dir = _write_fake_optimuskg_repo(tmp_path)
    monkeypatch.setenv("OPTIMUSKG_VENDOR_DIR", str(repo))
    monkeypatch.setenv("OPTIMUSKG_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("OPTIMUSKG_MAX_EDGES", "10")
    artifact = await optimuskg_context(
        ContextRequest(entities=_entities().model_dump(mode="json"))
    )
    assert artifact["edges"][0]["source"] == "optimuskg_parquet"
    assert artifact["edges"][0]["relation_type"] == "associated_with"
    assert "entity_disease" in artifact["missing_entities"]


@pytest.mark.asyncio
async def test_optimuskg_service_rejects_missing_real_parquet_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "optimuskg", raising=False)
    repo = tmp_path / "OptimusKG"
    _write_package(
        repo,
        "optimuskg",
        {
            "__init__.py": (
                "def get_file(relative_path, force=False):\n"
                "    raise FileNotFoundError(relative_path)\n"
            )
        },
    )
    monkeypatch.setenv("OPTIMUSKG_VENDOR_DIR", str(repo))
    with pytest.raises(Exception, match="OptimusKG parquet files are unavailable"):
        await optimuskg_context(ContextRequest(entities=_entities().model_dump(mode="json")))


@pytest.mark.asyncio
async def test_tooluniverse_service_runs_real_registry_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "tooluniverse", raising=False)
    repo = tmp_path / "ToolUniverse"
    _write_package(
        repo,
        "tooluniverse",
        {
            "__init__.py": """
class ToolUniverse:
    def __init__(self):
        self.all_tool_dict = {}
    def load_tools(self, include_tools=None, quiet=True, **kwargs):
        self.all_tool_dict = {name: {} for name in (include_tools or [])}
    def run_one_function(self, function_call_json, use_cache=False, validate=True, stream_callback=None):
        args = function_call_json.get('arguments', {})
        return {'summary': 'validated ' + args.get('disease_name', ''), 'args': args}
""",
        },
    )
    config_path = tmp_path / "workflows.json"
    config_path.write_text(
        json.dumps(
            {
                "required_workflows": [
                    "literature_validation",
                    "pathway_context",
                    "target_context",
                    "variant_context",
                    "trial_context_review",
                ],
                "workflows": {
                    workflow: {
                        "steps": [
                            {
                                "tool_name": "echo_disease",
                                "required_context": ["first_disease"],
                                "arguments": {"disease_name": "$first_disease"},
                            }
                        ]
                    }
                    for workflow in [
                        "literature_validation",
                        "pathway_context",
                        "target_context",
                        "variant_context",
                        "trial_context_review",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TOOLUNIVERSE_VENDOR_DIR", str(repo))
    monkeypatch.setenv("TOOLUNIVERSE_WORKFLOW_CONFIG", str(config_path))
    response = await tooluniverse_workflows(
        WorkflowRequest(
            workflows=["target_context"],
            entities=_entities().model_dump(mode="json"),
            graph=GraphEvidenceArtifact(
                artifact_id="artifact_graph",
                source_entity_ids=["entity_gene"],
                nodes=[],
                edges=[],
            ).model_dump(mode="json"),
        )
    )
    assert response["artifacts"][0]["summary"] == "validated dedifferentiated chondrosarcoma"
    assert response["artifacts"][0]["workflow"] == "target_context"


@pytest.mark.asyncio
async def test_medea_service_runs_vendored_entrypoint_with_local_vllm_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "Medea"
    _write_package(
        repo,
        "medea",
        {
            "__init__.py": """
LAST_RUNTIME = {}
def chat_completion(*args, **kwargs):
    LAST_RUNTIME["chat_completion_called"] = True
    return "local vllm response"
class LLMConfig:
    def __init__(self, config):
        self.config = config
class AgentLLM:
    def __init__(self, config, llm_name):
        self.config = config
        self.llm_name = llm_name
class LiteratureSearch:
    def __init__(self, model_name, verbose=False):
        self.model_name = model_name
class PaperJudge:
    def __init__(self, model_name, verbose=False):
        self.model_name = model_name
class OpenScholarReasoning:
    def __init__(self, tmp, llm_provider, verbose=False):
        self.llm_provider = llm_provider
class LiteratureReasoning:
    def __init__(self, llm, actions):
        self.llm = llm
        self.actions = actions

def literature_reasoning(query, literature_module):
    import os
    assert os.environ["LLM_PROVIDER_NAME"] == "OpenAI"
    assert os.environ["OPENAI_BASE_URL"] == "http://vllm:8000/v1"
    assert os.environ["OPENAI_API_KEY"] == "local-vllm"
    assert literature_module.llm.llm_name == "local-model"
    return {"final": "bounded reasoning for " + query[:40]}
""",
        },
    )
    monkeypatch.setenv("MEDEA_VENDOR_DIR", str(repo))
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    monkeypatch.setenv("VLLM_MODEL", "local-model")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    context = EvidenceContextBundle(
        artifact_id="artifact_context",
        extraction=ReportExtractionOutput(
            artifact_id="artifact_report",
            report_type="NGS",
            disease="dedifferentiated chondrosarcoma",
            specimen=None,
            tumor_percentage=None,
            molecular_findings=[
                MolecularFinding(
                    finding_id="finding_1",
                    gene="MTAP",
                    alteration="copy-number loss",
                    alteration_type="copy_number_loss",
                    source_page=1,
                    source_text="MTAP copy-number loss",
                    source_chunk_id="chunk_1",
                    confidence=0.8,
                )
            ],
            negative_findings=[],
            assay_limitations=[],
            source_file_id="file_1",
        ),
        graph_evidence=GraphEvidenceArtifact(
            artifact_id="artifact_graph",
            source_entity_ids=["entity_gene"],
            nodes=[],
            edges=[],
        ),
        tool_outputs=[],
        medea_reasoning=MedeaReasoningArtifact(
            artifact_id="artifact_empty",
            reasoning_mode="not_yet_run",
            summary="",
            supported_hypotheses=[],
            weakened_hypotheses=[],
        ),
    )
    artifact = await medea_reason(ReasonRequest(context=context.model_dump(mode="json")))
    assert artifact["reasoning_mode"] == "medea_literature_reasoning_local_vllm"
    assert artifact["requires_human_review"] is True
    assert "bounded reasoning" in artifact["summary"]


def test_medea_runtime_contract_requires_local_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "medea", raising=False)
    repo = tmp_path / "Medea"
    _write_package(
        repo,
        "medea",
        {
            "__init__.py": """
def chat_completion(*args, **kwargs):
    return 'local'
class LLMConfig:
    def __init__(self, config):
        self.config = config
class AgentLLM:
    def __init__(self, config, llm_name):
        self.llm_name = llm_name
class LiteratureSearch:
    def __init__(self, model_name, verbose=False):
        pass
class PaperJudge:
    def __init__(self, model_name, verbose=False):
        pass
class OpenScholarReasoning:
    def __init__(self, tmp, llm_provider, verbose=False):
        pass
class LiteratureReasoning:
    def __init__(self, llm, actions):
        pass
def literature_reasoning(query, literature_module):
    return {'final': 'ok'}
""",
        },
    )
    monkeypatch.setenv("MEDEA_VENDOR_DIR", str(repo))
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    monkeypatch.setenv("VLLM_MODEL", "local-model")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    payload = medea_runtime_contract()
    assert payload["local_model_configured"] is True
    assert payload["remote_provider_blocked"] is True
    assert payload["local_chat_completion_patched"] is True
    assert payload["patched_modules"]


def test_medea_runtime_contract_blocks_remote_provider_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "medea", raising=False)
    repo = tmp_path / "Medea"
    _write_package(
        repo,
        "medea",
        {
            "__init__.py": """
def chat_completion(*args, **kwargs):
    return 'local'
class LLMConfig: pass
class AgentLLM: pass
class LiteratureSearch: pass
class PaperJudge: pass
class OpenScholarReasoning: pass
class LiteratureReasoning: pass
def literature_reasoning(query, literature_module):
    return {'final': 'ok'}
""",
        },
    )
    monkeypatch.setenv("MEDEA_VENDOR_DIR", str(repo))
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    monkeypatch.setenv("VLLM_MODEL", "local-model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "real-remote-key")
    with pytest.raises(Exception, match="remote model-provider"):
        medea_runtime_contract()
