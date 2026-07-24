#!/usr/bin/env python3
"""Print auditable return signatures for Translume's MIMS provider boundaries.

This command intentionally does not call external services. It prints the exact
Pydantic contracts that the backend expects back from OptimusKG, ToolUniverse,
and Medea so developers can compare live REST responses against the local
schemas before wiring them into the clinical report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for package_src in (
    REPO_ROOT / "packages" / "translume-schemas" / "src",
    REPO_ROOT / "packages" / "translume-core" / "src",
):
    path = str(package_src)
    if path not in sys.path:
        sys.path.insert(0, path)

from translume_schemas.graph import GraphEvidenceArtifact  # noqa: E402
from translume_schemas.medea import MedeaReasoningArtifact  # noqa: E402
from translume_schemas.tools import ToolRunArtifact  # noqa: E402


PROVIDER_SIGNATURES: dict[str, dict[str, Any]] = {
    "optimuskg": {
        "provider_method": "graph_provider.retrieve_context(entities, retrieval_modes=...)",
        "rest_boundary": "OptimusKG graph context service",
        "return_type": "GraphEvidenceArtifact",
        "schema": GraphEvidenceArtifact.model_json_schema(),
        "clinical_use": (
            "Biomedical graph context, therapy-pressure subgraphs, resistance-path "
            "subgraphs, drug-target-biomarker links, and monitoring links."
        ),
    },
    "tooluniverse": {
        "provider_method": "tool_provider.run_workflows(entities=..., graph=..., workflows=...)",
        "rest_boundary": "ToolUniverse workflow service",
        "return_type": "list[ToolRunArtifact]",
        "item_schema": ToolRunArtifact.model_json_schema(),
        "clinical_use": (
            "Variant, target, pathway, therapy, guideline, clinical trial, "
            "resistance, biomarker re-testing, and lineage-transformation evidence."
        ),
    },
    "medea": {
        "provider_method": "reasoning_provider.reason_over_context(context)",
        "rest_boundary": "Medea bounded reasoning service",
        "return_type": "MedeaReasoningArtifact",
        "schema": MedeaReasoningArtifact.model_json_schema(),
        "clinical_use": (
            "Hypothesis support only for pathway adaptation, treatment pressure, "
            "escape forecasting, biomarker watch lists, and evidence limitations."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print MIMS provider return signatures for audit."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a readable report.",
    )
    args = parser.parse_args()
    if args.json:
        print(json.dumps(PROVIDER_SIGNATURES, indent=2, sort_keys=True))
        return 0
    for provider_name, signature in PROVIDER_SIGNATURES.items():
        print(f"\n## {provider_name}")
        print(f"Provider method: {signature['provider_method']}")
        print(f"REST boundary: {signature['rest_boundary']}")
        print(f"Expected return: {signature['return_type']}")
        print(f"Clinical use: {signature['clinical_use']}")
        schema = signature.get("schema") or signature.get("item_schema")
        print("Schema:")
        print(json.dumps(schema, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
