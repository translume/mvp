#!/usr/bin/env python3
"""Smoke-test local Reactome through the real ToolUniverse HTTP boundary."""

from __future__ import annotations

import argparse
import json

import httpx


def smoke_payload() -> dict[str, object]:
    """Return a deterministic pathway-context request for TP53."""
    return {
        "workflows": ["pathway_context"],
        "entities": {
            "artifact_id": "artifact_reactome_smoke_entities",
            "case_id": "case_reactome_smoke",
            "session_id": "session_reactome_smoke",
            "entities": [
                {
                    "entity_id": "entity_tp53",
                    "entity_type": "gene",
                    "original_text": "TP53",
                    "normalized_label": "TP53",
                    "source_finding_id": "finding_tp53",
                    "source_artifact_id": "artifact_reactome_smoke_report",
                    "needs_human_review": True,
                }
            ],
        },
        "graph": {
            "artifact_id": "artifact_reactome_smoke_graph",
            "source_entity_ids": ["entity_tp53"],
            "nodes": [],
            "edges": [],
            "retrieval_modes": [],
            "subgraphs": [],
        },
    }


def require_local_reactome_result(
    payload: object,
    expected_release: str,
) -> None:
    """Require local Reactome evidence and compatible pathway results."""
    if not isinstance(payload, dict):
        raise ValueError("ToolUniverse response must be a JSON object")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise ValueError("ToolUniverse response must contain one artifact")
    evidence = artifacts[0].get("evidence_items", [])
    reactome_items = [
        item
        for item in evidence
        if item.get("tool_name") == "ReactomeContent_search"
    ]
    if len(reactome_items) != 1:
        raise ValueError("ReactomeContent_search evidence is missing")
    item = reactome_items[0]
    data = json.loads(item["data"])
    metadata = json.loads(item["metadata"])
    results = data.get("results", [])
    if not results:
        raise ValueError("local Reactome returned no TP53 pathways")
    if not all(str(result.get("stId", "")).startswith("R-HSA-") for result in results):
        raise ValueError("local Reactome returned an invalid stable identifier")
    if metadata.get("remote_api_used") is not False:
        raise ValueError("Reactome evidence did not prove local execution")
    if str(metadata.get("configured_release")) != str(expected_release):
        raise ValueError("Reactome evidence release does not match expectation")
    vendor_names = {
        item.get("tool_name")
        for item in evidence
        if item.get("status") != "unavailable_external_source"
    }
    required = {
        "ReactomeContent_search",
        "PathwayCommons_search",
        "kegg_search_pathway",
    }
    if not required.issubset(vendor_names):
        raise ValueError("pathway_context did not execute all three sources")


def main() -> int:
    """Post the smoke request and validate the governed response."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-release", required=True)
    args = parser.parse_args()
    url = args.base_url.rstrip("/") + "/workflows"
    response = httpx.post(url, json=smoke_payload(), timeout=240)
    response.raise_for_status()
    require_local_reactome_result(response.json(), args.expected_release)
    print("Local Reactome ToolUniverse workflow smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
