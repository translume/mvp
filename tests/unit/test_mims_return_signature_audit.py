from __future__ import annotations

import json

from scripts.audit_mims_return_signatures import main, signature_records


def test_mims_return_signature_records_include_all_providers() -> None:
    records = signature_records()
    providers = {record["provider"] for record in records}

    assert providers == {"OptimusKG", "ToolUniverse", "Medea"}
    assert any(record["return_type"] == "GraphEvidenceArtifact" for record in records)
    assert any(record["return_type"] == "list[ToolRunArtifact]" for record in records)
    assert any(record["return_type"] == "MedeaReasoningArtifact" for record in records)


def test_mims_return_signature_cli_prints_text(capsys) -> None:
    exit_code = main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Provider: OptimusKG" in output
    assert "Client call: ToolUniverseServiceClient.run_workflows" in output
    assert "Return type: MedeaReasoningArtifact" in output


def test_mims_return_signature_cli_prints_json(capsys) -> None:
    exit_code = main(["--format", "json"])
    output = capsys.readouterr().out
    records = json.loads(output)

    assert exit_code == 0
    assert records[0]["provider"] == "OptimusKG"
    assert records[0]["fields"]
