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
import time
from pathlib import Path
from typing import Any, Sequence

from openai import OpenAI


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")
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
            "path": str(pathway_path.resolve()),
            "sha256": sha256_text(pathway_text),
            "headings": [item["heading"] for item in pathway_sections],
        },
        "research_memo": {
            "path": str(research_path.resolve()),
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
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return client.responses.create(
                model=model,
                reasoning={"effort": reasoning_effort},
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = 2 ** attempt
            print(
                f"API call failed; retrying {attempt}/{attempts} in {delay}s "
                f"({exc.__class__.__name__})...",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"OpenAI synthesis failed after {attempts} attempts: {last_error}")


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
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh"),
        default="high",
    )
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--request-timeout", type=float, default=600.0)
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
        print("[2/2] Generating tumor-board report (web search disabled)...", flush=True)
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=max(30.0, args.request_timeout),
            max_retries=0,
        )
        response = call_with_retries(
            client,
            model=args.model,
            system_prompt=system_prompt,
            user_message=user_message,
            attempts=max(1, args.max_attempts),
            reasoning_effort=args.reasoning_effort,
        )
        report = (response.output_text or "").strip()
        if not report:
            raise RuntimeError("The model returned an empty report.")

        report_path = args.output_dir / f"{args.output_name}.md"
        manifest_path = args.output_dir / f"{args.output_name}.manifest.json"
        report_path.write_text(report + "\n", encoding="utf-8")
        usage = response.usage.model_dump(mode="json") if response.usage else {}
        manifest = {
            "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "diagnosis": args.diagnosis,
            "model": getattr(response, "model", args.model),
            "response_id": getattr(response, "id", None),
            "reasoning_effort": args.reasoning_effort,
            "web_search_enabled": False,
            "system_prompt": str(prompt_path.resolve()),
            "system_prompt_sha256": sha256_text(prompt_template),
            "pathway_analysis": str(args.pathway_analysis.resolve()),
            "pathway_analysis_sha256": sha256_text(pathway_text),
            "research_memo": str(args.research_memo.resolve()),
            "research_memo_sha256": sha256_text(research_text),
            "report": str(report_path.resolve()),
            "usage": usage,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Report: {report_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
