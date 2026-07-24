# Tumor Board Causal Synthesis

Creates a tumor-board Markdown report from an existing pathway analysis and
research memo. It does not perform web searches.

## Setup

Activate the Python environment and set your API key:

```bash
source /Users/jennab/Desktop/prompts/precision_oncology_json_pipeline/.venv/bin/activate
export OPENAI_API_KEY="your-api-key"
```

Run commands from the `dynamic_pathway_analyzer` directory:

```bash
cd /Users/jennab/Desktop/prompts/precision_oncology_json_pipeline/precision_oncology_outputs/run_413db6bd63b56e57045f266ce591/dynamic_pathway_analyzer
```

## Run

```bash
python tumor_board_causal_synthesis.py \
  --pathway-analysis pathway_output/state_after_trial_prescreens.pathway_analysis.md \
  --research-memo pathway_output/state_after_trial_prescreens.research_memo.md \
  --diagnosis "dedifferentiated chondrosarcoma" \
  --output-dir tumor_board_output
```

## Arguments

- `--pathway-analysis`: pathway-analysis Markdown input.
- `--research-memo`: research-memo Markdown input.
- `--diagnosis`: diagnosis added to the synthesis prompt.
- `--output-dir`: directory for generated files.
- `--model`: optional model override.
- `--reasoning-effort`: optional `low`, `medium`, `high`, or `xhigh`.
- `--system-prompt`: optional path to a different system-prompt file.

## Outputs

```text
tumor_board_output/onco_board_summar.md
tumor_board_output/onco_board_summar.manifest.json
```

Open `onco_board_summar.md` for the completed report.
