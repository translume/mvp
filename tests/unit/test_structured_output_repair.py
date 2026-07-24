from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import BaseModel

from translume_core.compiler.structured_model_artifacts import _generate_artifact


class TinyArtifact(BaseModel):
    artifact_id: str
    value: str


class WrappedOutputProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        self.calls += 1
        return {"output": '{"value": "usable"}'}


class RepairingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.user_prompts: list[str] = []

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        self.calls += 1
        self.user_prompts.append(user_prompt)
        if self.calls == 1:
            return {"artifact_id": "artifact_wrong", "value": "bad"}
        return {"artifact_id": _planned_artifact_id(user_prompt), "value": "repaired"}


@pytest.mark.asyncio
async def test_structured_output_coerces_wrapped_json_and_adds_artifact_id(
    tmp_path: Path,
) -> None:
    _write_tiny_prompts(tmp_path)
    provider = WrappedOutputProvider()

    result = await _generate_artifact(
        prompt_name="tiny",
        schema_model=TinyArtifact,
        planned_artifact_id="artifact_tiny",
        payload={"input": "x"},
        source_artifact_ids=["artifact_source"],
        source_chunk_ids=["chunk_1"],
        source_file_id="file_1",
        model_provider=provider,
        model_name="test-model",
        prompts_root=tmp_path,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert provider.calls == 1
    assert result.artifact.artifact_id == "artifact_tiny"
    assert result.artifact.value == "usable"
    assert result.provenance.generation_status == "generated"


@pytest.mark.asyncio
async def test_structured_output_retries_with_repair_prompt_after_bad_artifact_id(
    tmp_path: Path,
) -> None:
    _write_tiny_prompts(tmp_path)
    provider = RepairingProvider()

    result = await _generate_artifact(
        prompt_name="tiny",
        schema_model=TinyArtifact,
        planned_artifact_id="artifact_tiny_repair",
        payload={"input": "x"},
        source_artifact_ids=["artifact_source"],
        model_provider=provider,
        model_name="test-model",
        prompts_root=tmp_path,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert provider.calls == 2
    assert "Previous structured-output attempt failed validation" in provider.user_prompts[1]
    assert result.artifact.value == "repaired"
    assert result.provenance.generation_status == (
        "generated_after_structured_output_repair"
    )


def _write_tiny_prompts(path: Path) -> None:
    path.joinpath("tiny_system.md").write_text("Return JSON only.", encoding="utf-8")
    path.joinpath("tiny_user.md").write_text(
        "The artifact_id must be exactly:\n{planned_artifact_id}\n\n{payload_json}",
        encoding="utf-8",
    )


def _planned_artifact_id(user_prompt: str) -> str:
    lines = user_prompt.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "The artifact_id must be exactly:" and index + 1 < len(lines):
            return lines[index + 1].strip()
    raise AssertionError("planned artifact id missing from prompt")
