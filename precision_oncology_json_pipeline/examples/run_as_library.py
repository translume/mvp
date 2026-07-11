"""Minimal library integration example.

Run from the project root after setting OPENAI_API_KEY.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from precision_oncology_pipeline import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_REASONING_EFFORT,
    PipelineConfig,
    run_pipeline,
)


async def main() -> None:
    input_path = Path("/path/to/translume_review_packet.json")
    output_dir = Path("precision_oncology_outputs")

    config = PipelineConfig(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        reasoning_effort=OPENAI_REASONING_EFFORT,
        output_dir=output_dir,
        max_concurrency=4,
        max_research_jobs=24,
        max_sources_per_job=5,
        max_sources_per_hypothesis=10,
        max_sources_total=24,
        strict_source_verification=True,
        enable_web_search=True,
        live_web_access=True,
        resume=True,
        store_prompt_payloads=False,
        run_llm_validators=True,
    )

    result = await run_pipeline(
        input_path=input_path,
        config=config,
        actionable_override_path=None,
        clinical_overlay_path=None,
    )
    print(result.final_json_path)


if __name__ == "__main__":
    asyncio.run(main())
