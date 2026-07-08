from __future__ import annotations

import json

from translume_core.compiler.decision_brief import _with_prompt_budget


def test_decision_prompt_budget_compacts_large_payload_for_local_model() -> None:
    payload = {
        "task": "translational_assessment",
        "questions": [{"question_key": "target_relevance", "question": "q"}],
        "tool_outputs": [
            {"summary": "x" * 6000, "evidence_items": ["y" * 4000]}
            for _index in range(60)
        ],
        "graph_evidence": {
            "nodes": [{"label": "node" + str(index), "text": "z" * 5000} for index in range(80)],
            "edges": [{"relation": "associated_with", "text": "r" * 5000} for _ in range(80)],
        },
        "missing_evidence": ["m" * 4000 for _ in range(30)],
    }

    compact = _with_prompt_budget("translational_assessment", payload)
    budget = compact["prompt_budget"]

    assert budget["stage_name"] == "translational_assessment"
    assert budget["original_chars"] > budget["char_budget"]
    assert len(json.dumps(compact, sort_keys=True)) < budget["original_chars"]
    assert budget["compacted"] is True
    assert "local GPU execution" in budget["operator_note"]
