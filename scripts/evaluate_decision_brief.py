from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from translume_core.evaluation.decision_brief import (
    evaluate_decision_brief_against_fixture,
    evaluate_review_packet_against_fixture,
    load_decision_brief_evaluation_fixture,
)
from translume_schemas.decision_brief import OncologistDecisionBrief
from translume_schemas.evaluation import DecisionBriefEvaluationFixture
from translume_schemas.evaluation import DecisionBriefEvaluationReport
from translume_schemas.export import ReviewPacketExport


def main() -> int:
    """Run deterministic decision-brief evaluation from JSON files.

    Acceptance criteria:
        1. Reads either a review packet JSON or decision brief JSON.
        2. Reads a fixture JSON with expected/forbidden clinical signals.
        3. Prints a serialized evaluation report.
        4. Writes the report to `--output` when requested.
        5. Returns non-zero only when evaluation fails or inputs are invalid.

    Returns:
        Process exit code.
    """
    args = _parse_args()
    fixture = load_decision_brief_evaluation_fixture(
        _read_json_mapping(args.fixture)
    )
    report = _evaluate_from_args(args=args, fixture=fixture)
    rendered = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.passed else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a Translume decision brief against an NGS fixture.",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--packet",
        type=Path,
        help="Path to a ReviewPacketExport JSON file.",
    )
    input_group.add_argument(
        "--brief",
        type=Path,
        help="Path to an OncologistDecisionBrief JSON file.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="Path to a decision-brief evaluation fixture JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the evaluation report JSON.",
    )
    return parser.parse_args()


def _evaluate_from_args(
    *,
    args: argparse.Namespace,
    fixture: DecisionBriefEvaluationFixture,
) -> DecisionBriefEvaluationReport:
    if args.packet is not None:
        packet = ReviewPacketExport.model_validate(_read_json_mapping(args.packet))
        return evaluate_review_packet_against_fixture(
            packet=packet,
            fixture=fixture,
        )
    if args.brief is not None:
        brief = OncologistDecisionBrief.model_validate(_read_json_mapping(args.brief))
        return evaluate_decision_brief_against_fixture(
            brief=brief,
            fixture=fixture,
        )
    raise ValueError("Either --packet or --brief is required")


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
