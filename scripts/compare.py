#!/usr/bin/env python3
"""
Compare Needle routing vs Gemini Nano routing on the same test set.

Requires:
  - needle_rs Python package (pip install -r scripts/requirements.txt)
  - chrome-ai bridge running (python3 server.py, bridge page open in Chrome)

Usage:
  python3 scripts/compare.py \
    --needle-model output/needle.safetensors \
    --test data/needle/test.jsonl
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


BRIDGE_URL = "http://localhost:8462"


def bridge_route(query: str, tools: str) -> dict | None:
    """Route a query through Gemini Nano via the chrome-ai bridge."""
    try:
        body = json.dumps({"api": "agent-route", "query": query, "tools": tools}).encode()
        req = urllib.request.Request(f"{BRIDGE_URL}/prompt", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        job_id = data["id"]
        # Poll for result
        import time
        deadline = time.time() + 60
        while time.time() < deadline:
            with urllib.request.urlopen(f"{BRIDGE_URL}/result/{job_id}") as resp:
                result = json.loads(resp.read())
            if result["status"] == "done":
                return json.loads(result["text"])
            if result["status"] == "error":
                print(f"  Bridge error: {result.get('error', 'unknown')}", file=sys.stderr)
                return None
            time.sleep(1)
        print(f"  Bridge timeout for: {query[:50]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Bridge error: {e}", file=sys.stderr)
        return None


def needle_route(model, query: str, tools: str) -> dict | None:
    """Route a query through the exported Needle model."""
    try:
        raw = model.route(query, tools)
        return json.loads(raw)
    except Exception as e:
        print(f"  Needle error: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Compare Needle vs Gemini Nano routing accuracy"
    )
    parser.add_argument("--needle-model", required=True,
                        help="Path to exported .safetensors model")
    parser.add_argument("--test", required=True,
                        help="Path to test.jsonl")
    args = parser.parse_args()

    # Load Needle model
    from pathlib import Path
    model_path = Path(args.needle_model)
    vocab = str(model_path.parent / "vocab.txt")
    if not Path(vocab).exists():
        vocab = str(model_path.with_suffix("") + "_vocab.txt")

    print(f"Loading Needle model: {args.needle_model}")
    from needle_rs import NeedleModel
    needle = NeedleModel(args.needle_model, vocab)

    # Check bridge
    try:
        with urllib.request.urlopen(f"{BRIDGE_URL}/health") as resp:
            health = json.loads(resp.read())
            if not health.get("ok"):
                print("chrome-ai bridge not healthy. Start: python3 server.py", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"chrome-ai bridge not reachable at {BRIDGE_URL}: {e}", file=sys.stderr)
        print("Start: python3 server.py and open the bridge page in Chrome", file=sys.stderr)
        sys.exit(1)
    print(f"Bridge OK at {BRIDGE_URL}")

    # Load test data
    with open(args.test) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    # Sample: compare on a subset (bridge is slow)
    sample = lines[:200] if len(lines) > 200 else lines
    print(f"Comparing {len(sample)} queries (sampled from {len(lines)} total)\n")

    needle_correct = 0
    bridge_correct = 0
    total = len(sample)

    for i, rec in enumerate(sample):
        expected = json.loads(rec["answers"])
        expected_name = expected[0]["name"] if expected else None

        n_result = needle_route(needle, rec["query"], rec["tools"])
        b_result = bridge_route(rec["query"], rec["tools"])

        n_ok = (n_result or {}).get("name") == expected_name
        b_ok = (b_result or {}).get("name") == expected_name

        if n_ok:
            needle_correct += 1
        if b_ok:
            bridge_correct += 1

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{total} — Needle: {needle_correct/(i+1)*100:.1f}%  Bridge: {bridge_correct/(i+1)*100:.1f}%")

    print(f"\n{'='*50}")
    print(f"  Needle (exported):     {needle_correct}/{total} ({needle_correct/total*100:.1f}%)")
    print(f"  Gemini Nano (bridge):  {bridge_correct}/{total} ({bridge_correct/total*100:.1f}%)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()