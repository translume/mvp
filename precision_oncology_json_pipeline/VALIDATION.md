# Validation record

Validation date: 2026-07-10

## Static and automated checks

```text
python -m py_compile precision_oncology_pipeline.py     PASS
ruff check precision_oncology_pipeline.py tests examples PASS
mypy --ignore-missing-imports ...                       PASS
python -m pytest                                        10 passed
```

The automated suite includes a fully mocked end-to-end OpenAI Responses API run. It verifies that the pipeline emits a complete `FinalPacket`, preserves a canonical ClinicalTrials.gov URL, creates a trial pre-screen, and generates a dynamic URL-candidate-fit appendix section.

## Supplied JSON parse-only test

The tool was run in `--dry-run` mode against the supplied Translume review-packet JSON. It completed successfully with deterministic run ID:

```text
run_413db6bd63b56e57045f266ce591
```

The conservative fallback parser recovered:

```text
Disease/histology: Dedifferentiated chondrosarcoma
Specimen: Soft tissue / chest wall
Primary actionable findings: CDKN2A, CHEK2, MTAP
Secondary/context findings: AKT2, CDKN2B, LYN, TP53
Primary technical finding: TAF1 low coverage
```

This parse-only result is intended to validate the adapter and does not replace the user's production actionable-item plucker.

## Live API status

No live OpenAI API request was executed in the build environment because no `OPENAI_API_KEY` was available. Use `--quick-test` for the first live run, inspect the resulting JSON, and then run without that flag for the full evidence fan-out and validator passes.
