#!/bin/bash
# Fine-tune Needle on tool routing data.
#
# Prerequisites:
#   pip install -r scripts/requirements.txt
#   chrome-ai generate --tools tools.json  (if data not already generated)
#
# Usage:
#   bash scripts/fine-tune.sh

set -euo pipefail

DATA_DIR="data/needle"
OUTPUT_DIR="output"
CHECKPOINT_DIR="checkpoints"

mkdir -p "$OUTPUT_DIR" "$CHECKPOINT_DIR"

echo "━━━ Needle Fine-tune Pipeline ━━━"
echo "Data: $DATA_DIR"
echo "Checkpoints: $CHECKPOINT_DIR"
echo "Output: $OUTPUT_DIR"
echo ""

# 1. Combine train + val for the upstream CLI
echo "→ Combining train + val..."
cat "$DATA_DIR/train.jsonl" "$DATA_DIR/val.jsonl" > /tmp/needle_train_all.jsonl
echo "  $(wc -l < /tmp/needle_train_all.jsonl) examples"

# 2. Fine-tune (upstream Python)
echo ""
echo "→ Fine-tuning Needle (~26 hours)..."
needle finetune /tmp/needle_train_all.jsonl
echo "  Done."

# 3. Find the best checkpoint
CHECKPOINT=$(ls checkpoints/needle_finetuned_*_best.pkl 2>/dev/null | tail -1)
if [ -z "$CHECKPOINT" ]; then
  echo "  Error: no checkpoint found in $CHECKPOINT_DIR/"
  exit 1
fi
echo "  Best checkpoint: $CHECKPOINT"

# 4. Convert to SafeTensors for needle-rs
echo ""
echo "→ Converting to SafeTensors..."
python3 scripts/export.py \
  --checkpoint "$CHECKPOINT" \
  --output-dir "$OUTPUT_DIR" \
  --quantize int4
echo "  Weights in $OUTPUT_DIR/"
ls -lh "$OUTPUT_DIR/"

# 5. Evaluate on test set
echo ""
echo "→ Evaluating on test set..."
needle eval --checkpoint "$CHECKPOINT" --test "$DATA_DIR/test.jsonl"

echo ""
echo "━━━ Done ━━━"
echo "Next: review metrics above. If acceptable, deploy the weights from $OUTPUT_DIR/."