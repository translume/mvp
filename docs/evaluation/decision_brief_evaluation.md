# Decision Brief Evaluation Harness

Phase 6 adds a deterministic evaluation harness for the oncologist decision
brief. The harness compares a generated `OncologistDecisionBrief` or full
`ReviewPacketExport` against an NGS fixture that declares expected clinical
signals, forbidden signals, and pass/fail thresholds.

## What it scores

- Expected signal recall across findings, treatment options, resistance routes,
  biomarkers, test modalities, and clinical events.
- Forbidden or unsupported clinical terms introduced by the brief.
- Unsupported certainty language such as guaranteed response or cure claims.
- Row-level evidence coverage for treatment, pressure, resistance, biomarker,
  re-testing, and next-test rows.
- Clinical usefulness based on whether the decision-facing sections are
  populated.

## Run from CLI

```bash
uv run python scripts/evaluate_decision_brief.py \
  --packet translume_review_packet_export.json \
  --fixture tests/fixtures/decision_brief/ngs_lung_egfr_resistance_fixture.json \
  --output /tmp/translume-decision-brief-eval.json
```

Use `--brief` instead of `--packet` when evaluating a standalone
`OncologistDecisionBrief` JSON artifact.

The command exits with code `0` when the report passes the fixture thresholds and
`1` when it fails.
