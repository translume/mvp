#!/usr/bin/env python3
"""Create a tumor-board causal report from two existing Markdown artifacts.

This program performs no web search. It uses the pathway analysis and research
memo as the complete evidence boundary for one final OpenAI synthesis call.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from openai import OpenAI

if __package__:
    from . import openai_runtime as remote
else:
    import openai_runtime as remote


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv(
    "OPENAI_REASONING_MODEL", os.getenv("OPENAI_MODEL", "gpt-6-astra")
)
OPENAI_REASONING_MODE = os.getenv("OPENAI_REASONING_MODE", "pro")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "xhigh")
DEFAULT_PROMPT_NAME = "tumor_board_causal_synthesis_prompt.md"

# The supplied attachment remains a fallback until it is copied beside this
# script under DEFAULT_PROMPT_NAME. --system-prompt always takes precedence.
SUPPLIED_PROMPT_FALLBACK = Path("./fallback-prompt.txt")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_text(path: Path, label: str) -> str:
    if not path.exists():
        raise ValueError(f"{label} does not exist: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{label} is empty: {path}")
    return text


def parse_markdown_sections(text: str) -> list[dict[str, Any]]:
    """Split Markdown into an ordered heading/content map without losing text."""

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return [{"level": 0, "heading": "Document", "content": text}]

    sections: list[dict[str, Any]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append({"level": 0, "heading": "Preamble", "content": preamble})
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            {
                "level": len(match.group(1)),
                "heading": match.group(2).strip(),
                "content": text[match.end() : end].strip(),
            }
        )
    return sections


def resolve_prompt_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    local = Path(__file__).resolve().with_name(DEFAULT_PROMPT_NAME)
    if local.exists():
        return local
    if SUPPLIED_PROMPT_FALLBACK.exists():
        return SUPPLIED_PROMPT_FALLBACK
    raise ValueError(
        "System prompt was not found. Pass --system-prompt or place "
        f"{DEFAULT_PROMPT_NAME} beside this script."
    )


def prepare_system_prompt(template: str, diagnosis: str) -> str:
    """Resolve prompt placeholders while keeping the supplied prompt intact."""

    prompt = template.replace("{{AUTHORITATIVE_DIAGNOSIS}}", diagnosis)
    unavailable = (
        "Not separately supplied. Extract only what is explicitly reported in "
        "the pathway-analysis and research-memo Markdown documents."
    )
    placeholders = [
        "PATIENT_AND_DISEASE_CONTEXT_JSON",
        "PATHOLOGY_JSON",
        "MOLECULAR_FINDINGS_JSON",
        "MULTIOMIC_FINDINGS_JSON",
        "IMAGING_JSON",
        "TREATMENT_HISTORY_JSON",
        "CLINICAL_STATUS_JSON",
        "LABORATORY_JSON",
        "CLINICAL_TRIALS_JSON",
        "EVIDENCE_JSON",
        "ADDITIONAL_SOURCE_TEXT",
    ]
    for placeholder in placeholders:
        prompt = prompt.replace(f"{{{{{placeholder}}}}}", unavailable)
    return prompt


def build_user_message(
    diagnosis: str,
    pathway_path: Path,
    pathway_text: str,
    research_path: Path,
    research_text: str,
) -> str:
    pathway_sections = parse_markdown_sections(pathway_text)
    research_sections = parse_markdown_sections(research_text)
    index = {
        "diagnosis": diagnosis,
        "pathway_analysis": {
            "document": "pathway_analysis",
            "sha256": sha256_text(pathway_text),
            "headings": [item["heading"] for item in pathway_sections],
        },
        "research_memo": {
            "document": "research_memo",
            "sha256": sha256_text(research_text),
            "headings": [item["heading"] for item in research_sections],
        },
    }
    return "\n".join(
        [
            f"Diagnosis: {diagnosis}",
            "",
            "Use only the two supplied Markdown documents below. Do not browse,",
            "retrieve new sources, invent missing clinical facts, or cite a URL",
            "that is not present in these documents.",
            "",
            "DOCUMENT INDEX",
            "```json",
            json.dumps(index, indent=2, ensure_ascii=False),
            "```",
            "",
            "PATHWAY ANALYSIS MARKDOWN",
            "```markdown",
            pathway_text,
            "```",
            "",
            "RESEARCH MEMO MARKDOWN",
            "```markdown",
            research_text,
            "```",
            "",
            "Produce the requested Molecular Tumor Board Causal Summary and",
            "Adaptive Action Plan now, following the exact system-prompt headings.",
        ]
    )


def call_with_retries(
    client: OpenAI,
    *,
    model: str,
    system_prompt: str,
    user_message: str,
    attempts: int,
    reasoning_effort: str,
    reasoning_mode: str = "pro",
    max_output_tokens: int = 32_000,
    audit_dir: Path | None = None,
) -> Any:
    """Synthesize remotely with explicit storage policy and bounded retries."""
    settings = remote.RemoteSettings(
        reasoning_mode=reasoning_mode,
        reasoning_effort=reasoning_effort,
        max_attempts=attempts,
        max_output_tokens=max_output_tokens,
        max_retry_output_tokens=max(max_output_tokens, 64_000),
    )
    return remote.request_response(
        client,
        stage="tumor_board_synthesis",
        settings=settings,
        audit_dir=audit_dir,
        request={
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        },
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a no-web Molecular Tumor Board Causal Summary from an "
            "existing pathway-analysis Markdown file and research memo."
        )
    )
    parser.add_argument("--pathway-analysis", type=Path, required=True)
    parser.add_argument("--research-memo", type=Path, required=True)
    parser.add_argument("--diagnosis", required=True)
    parser.add_argument(
        "--system-prompt",
        type=Path,
        help=(
            f"Prompt file; defaults to {DEFAULT_PROMPT_NAME} beside this script, "
            "then the originally supplied prompt attachment."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("tumor_board_output"))
    parser.add_argument("--output-name", default="onco_board_summary")
    parser.add_argument("--model", default=OPENAI_MODEL)
    parser.add_argument(
        "--reasoning-mode", choices=("pro",), default=OPENAI_REASONING_MODE
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default=OPENAI_REASONING_EFFORT,
    )
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=float(os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "900")),
    )
    parser.add_argument("--max-output-tokens", type=int, default=32_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    try:
        prompt_path = resolve_prompt_path(args.system_prompt)
        prompt_template = read_text(prompt_path, "System prompt")
        pathway_text = read_text(args.pathway_analysis, "Pathway analysis")
        research_text = read_text(args.research_memo, "Research memo")
        system_prompt = prepare_system_prompt(prompt_template, args.diagnosis)
        user_message = build_user_message(
            args.diagnosis,
            args.pathway_analysis,
            pathway_text,
            args.research_memo,
            research_text,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)

        print("[1/2] Parsed both Markdown source documents.", flush=True)
        print(
            "[2/2] Generating tumor-board report (web search disabled)...", flush=True
        )
        settings = remote.RemoteSettings(
            reasoning_mode=args.reasoning_mode,
            reasoning_effort=args.reasoning_effort,
            request_timeout_seconds=args.request_timeout,
            max_attempts=args.max_attempts,
            max_output_tokens=args.max_output_tokens,
            max_retry_output_tokens=max(args.max_output_tokens, 64_000),
        )
        with remote.build_client(OPENAI_API_KEY, settings) as client:
            response = call_with_retries(
                client,
                model=args.model,
                system_prompt=system_prompt,
                user_message=user_message,
                attempts=args.max_attempts,
                reasoning_effort=args.reasoning_effort,
                reasoning_mode=args.reasoning_mode,
                max_output_tokens=args.max_output_tokens,
                audit_dir=args.output_dir / "openai_calls",
            )
        report = (response.output_text or "").strip()
        if not report:
            raise RuntimeError("The model returned an empty report.")

        report_path = args.output_dir / f"{args.output_name}.md"
        manifest_path = args.output_dir / f"{args.output_name}.manifest.json"
        remote.write_text_atomic(report_path, report + "\n")
        metadata = remote.response_metadata(response)
        usage = metadata["usage"]
        manifest = {
            "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "diagnosis": args.diagnosis,
            "model": getattr(response, "model", args.model),
            "response_id": getattr(response, "id", None),
            "request_id": metadata["request_id"],
            "provider": "openai",
            "reasoning_mode": args.reasoning_mode,
            "store": False,
            "status": metadata["status"],
            "reasoning_effort": args.reasoning_effort,
            "web_search_enabled": False,
            "system_prompt": str(prompt_path.resolve()),
            "system_prompt_sha256": sha256_text(prompt_template),
            "pathway_analysis": str(args.pathway_analysis.resolve()),
            "pathway_analysis_sha256": sha256_text(pathway_text),
            "research_memo": str(args.research_memo.resolve()),
            "research_memo_sha256": sha256_text(research_text),
            "report": str(report_path.resolve()),
            "report_sha256": sha256_text(report + "\n"),
            "audit_directory": str((args.output_dir / "openai_calls").resolve()),
            "usage": usage,
        }
        remote.write_json_atomic(manifest_path, manifest)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Report: {report_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
