#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/review_packet.json [output_dir]" >&2
  exit 2
fi

INPUT_JSON="$1"
OUTPUT_DIR="${2:-precision_oncology_outputs}"
MODEL="${OPENAI_MODEL:-gpt-5.6-luna}"
EFFORT="${OPENAI_REASONING_EFFORT:-medium}"

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this script}"

python precision_oncology_pipeline.py \
  --input "$INPUT_JSON" \
  --output-dir "$OUTPUT_DIR" \
  --model "$MODEL" \
  --reasoning-effort "$EFFORT" \
  --quick-test
