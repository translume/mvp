from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


RETURN_SIGNATURES: tuple[dict[str, object], ...] = (
    {
        "provider": "OptimusKG",
        "client": "OptimusKGServiceClient.retrieve_context",
        "endpoint": "POST /context",
        "return_type": "GraphEvidenceArtifact",
        "model": GraphEvidenceArtifact,
    },
    {
        "provider": "ToolUniverse",
        "client": "ToolUniverseServiceClient.run_workflows",
        "endpoint": "POST /workflows",
        "return_type": "list[ToolRunArtifact]",
        "model": ToolRunArtifact,
    },
    {
        "provider": "Medea",
        "client": "MedeaServiceClient.reason_over_context",
        "endpoint": "POST /reason",
        "return_type": "MedeaReasoningArtifact",
        "model": MedeaReasoningArtifact,
    },
)


def signature_records() -> list[dict[str, object]]:
    """Return audit records for third-party MIMS return signatures.

    Acceptance criteria:
        1. Determinism: Return order is stable across invocations.
        2. No network: The function does not call any MIMS service.
        3. Auditability: Every record names provider, client, endpoint, and return
           model fields.
        4. Validation: Records are derived from Pydantic schema models.
    """
    return [
        {
            "provider": str(item["provider"]),
            "client": str(item["client"]),
            "endpoint": str(item["endpoint"]),
            "return_type": str(item["return_type"]),
            "fields": _model_fields(item["model"]),
            "json_schema": item["model"].model_json_schema(),
        }
        for item in RETURN_SIGNATURES
    ]


def _model_fields(model: object) -> list[dict[str, object]]:
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError("model must be a Pydantic BaseModel class")
    return [
        {
            "name": name,
            "annotation": _annotation_name(field.annotation),
            "required": field.is_required(),
            "default": None if field.is_required() else field.default,
        }
        for name, field in model.model_fields.items()
    ]


def _annotation_name(annotation: object) -> str:
    return str(annotation).replace("typing.", "")


def render_text(records: Sequence[dict[str, object]]) -> str:
    """Render MIMS return signatures as operator-readable text."""
    sections: list[str] = []
    for record in records:
        sections.append(
            "\n".join(
                [
                    f"Provider: {record['provider']}",
                    f"Client call: {record['client']}",
                    f"Endpoint: {record['endpoint']}",
                    f"Return type: {record['return_type']}",
                    "Fields:",
                    *_field_lines(record["fields"]),
                ]
            )
        )
    return "\n\n".join(sections)


def _field_lines(fields: object) -> list[str]:
    if not isinstance(fields, Iterable):
        return []
    lines = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        required = "required" if field.get("required") else "optional"
        lines.append(
            f"  - {field.get('name')}: {field.get('annotation')} ({required})"
        )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Print third-party MIMS return signatures for audit.

    Acceptance criteria:
        1. Defaults to text output for terminal review.
        2. Supports JSON output for machine diffing.
        3. Performs no network I/O or service calls.
        4. Returns zero after successful rendering.
    """
    parser = argparse.ArgumentParser(
        description="Print third-party MIMS return signatures for audit.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    records = signature_records()
    if args.format == "json":
        print(json.dumps(records, indent=2, sort_keys=True, default=str))
    else:
        print(render_text(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
