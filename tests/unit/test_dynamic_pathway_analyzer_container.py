from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dynamic_pathway_analyzer_dockerfile_contract() -> None:
    """The analyzer image should use the approved persistent-service pattern."""
    dockerfile = (
        ROOT / "docker" / "dynamic-pathway-analyzer.Dockerfile"
    ).read_text(encoding="utf-8")

    assert "FROM python:3.12.13-slim" in dockerfile
    assert "dynamic_pathway_analyzer/requirements.txt" in dockerfile
    assert 'CMD ["sleep", "infinity"]' in dockerfile
    assert "dynamic-pathway-analyzer-entrypoint" in dockerfile

    entrypoint = (
        ROOT / "docker" / "dynamic-pathway-analyzer-entrypoint.sh"
    ).read_text(encoding="utf-8")
    assert 'runtime_uid="${DYNAMIC_PATHWAY_UID:-1000}"' in entrypoint
    assert 'runtime_gid="${DYNAMIC_PATHWAY_GID:-1000}"' in entrypoint
    assert 'exec runuser --user analyzer -- "$@"' in entrypoint


def test_dynamic_pathway_analyzer_compose_contract() -> None:
    """Compose should mount the workspace and pass analyzer configuration."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "  dynamic-pathway-analyzer:" in compose
    assert "docker/dynamic-pathway-analyzer.Dockerfile" in compose
    assert '"./dynamic_pathway_analyzer:/app"' in compose
    assert "DYNAMIC_PATHWAY_UID: ${DYNAMIC_PATHWAY_UID:-1000}" in compose
    assert "DYNAMIC_PATHWAY_GID: ${DYNAMIC_PATHWAY_GID:-1000}" in compose
    assert "OPENAI_NORMALIZER_MODEL:" in compose
    assert "MAX_RESEARCH_PATHWAYS:" in compose


def test_analyzer_sources_do_not_embed_api_key_fallbacks() -> None:
    """Analyzer scripts should require credentials from their environment."""
    source_paths = (
        ROOT / "dynamic_pathway_analyzer" / "dynamic_pathway_analyzer.py",
        ROOT
        / "dynamic_pathway_analyzer"
        / "tumor_board_causal_synthesis.py",
    )

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        assert 'OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")' in source
