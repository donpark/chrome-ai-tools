#!/usr/bin/env python3
"""
Evaluate an exported Needle .safetensors model against a test.jsonl file.

Usage:
  # Test exported safetensors model (needle-rs runtime)
  python3 scripts/eval.py --model output/needle.safetensors --test data/needle/test.jsonl

  # Test training checkpoint (needle training package)
  python3 scripts/eval.py --checkpoint checkpoints/needle_finetuned_best.pkl --test data/needle/test.jsonl
"""

import argparse
import json
import sys


def eval_safetensors(model_path: str, test_path: str):
    """Evaluate via needle_rs (the exported WASM-compiled runtime)."""
    try:
        from needle_rs import NeedleModel
    except ImportError:
        print("needle_rs not installed. Run: pip install -r scripts/requirements.txt")
        sys.exit(1)

    vocab = model_path.replace(".safetensors", "_vocab.txt")
    if not vocab:
        # Try adjacent vocab.txt in same directory
        from pathlib import Path
        candidate = Path(model_path).parent / "vocab.txt"
        if candidate.exists():
            vocab = str(candidate)

    print(f"Loading model: {model_path}")
    model = NeedleModel(model_path, vocab)

    with open(test_path) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    correct = 0
    total = len(lines)
    for i, rec in enumerate(lines):
        expected = json.loads(rec["answers"])
        expected_name = expected[0]["name"] if expected else None
        pred = json.loads(model.route(rec["query"], rec["tools"]))
        pred_name = pred.get("name") if pred else None
        ok = pred_name == expected_name
        if ok:
            correct += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{total} — {correct/(i+1)*100:.1f}%")

    pct = correct / total * 100 if total else 0
    print(f"\nResults: {correct}/{total} correct ({pct:.1f}%)")


def eval_checkpoint(checkpoint_path: str, test_path: str):
    """Evaluate via the training package's `needle eval` command."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "needle", "eval",
         "--checkpoint", checkpoint_path, "--test", test_path],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Evaluate Needle model")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model", help="Path to exported .safetensors model")
    group.add_argument("--checkpoint", help="Path to training .pkl checkpoint")
    parser.add_argument("--test", required=True, help="Path to test.jsonl")
    args = parser.parse_args()

    if args.model:
        eval_safetensors(args.model, args.test)
    else:
        eval_checkpoint(args.checkpoint, args.test)


if __name__ == "__main__":
    main()