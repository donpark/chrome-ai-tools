# Needle Tool Routing

chrome-ai-tools can train, export, and test Needle models for tool routing —
a small transformer that maps natural language queries to tool calls, running
entirely in-browser via the `needle-rs` WASM runtime (~258 KB).

## Quick start

```bash
# 1. Install Python deps
pip install -r scripts/requirements.txt

# 2. Write tool definitions (see schema below)
cat > tools.json << 'EOF'
[
  {"name": "summarize_page", "description": "Summarize the page content", "inputSchema": {"type": "object", "properties": {}, "required": []}},
  {"name": "lookup_posts", "description": "Find related posts on this page", "inputSchema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": []}}
]
EOF

# 3. Generate training data
chrome-ai generate --tools tools.json --output data/needle

# 4. Fine-tune the model
bash scripts/fine-tune.sh
```

## Tool schema

Each tool definition must have:

| Field | Type | Description |
|---|---|---|
| `name` | string | Lowercase snake_case identifier (e.g. `summarize_page`) |
| `description` | string | Natural language description of what the tool does |
| `inputSchema` | object | JSON Schema (`type: "object"` with `properties` and optional `required`) |

Example:

```json
{
  "name": "lookup_posts",
  "description": "Find related posts on this page",
  "inputSchema": {
    "type": "object",
    "properties": {
      "summary": {
        "type": "string",
        "description": "Text to match against existing posts"
      }
    },
    "required": ["summary"]
  }
}
```

## Training data format

JSONL (one JSON object per line). Each record:

```json
{"query":"...","tools":"...","answers":"..."}
```

| Field | Type | Description |
|---|---|---|
| `query` | string | Natural language user query |
| `tools` | string | JSON-stringified `ToolDefinition[]` — available tools at inference time |
| `answers` | string | JSON-stringified `[{"name":"tool_name","arguments":{...}}]` — empty array `[]` means abstain |

## Generation modes

### Schematic mode (default)

Generates examples programmatically from tool schemas—no API key needed. Creates
positive examples per tool, null/unsupported queries, and contrastive/ambiguous
pairs between similar tools.

```bash
chrome-ai generate --tools tools.json --output data/needle
```

### LLM mode (Gemini)

Uses the Gemini API to generate diverse natural-language phrasings for each tool.
Pass an `llm` function to `generateTrainingData()` in TypeScript:

```ts
import { GoogleGenerativeAI } from '@google/generative-ai';
import { generateTrainingData } from 'chrome-ai-tools';

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);
const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

await generateTrainingData(tools, {
  llm: async (prompt, tools) => {
    const res = await model.generateContent(
      `Generate 20 diverse user queries for: ${prompt}\n` +
      `Available tools: ${tools.map(t => t.name).join(', ')}\n` +
      `Return one per line, no numbering.`
    );
    return res.response.text().trim().split('\n').filter(Boolean);
  },
});
```

## Export

Convert a fine-tuned `.pkl` checkpoint to the `.safetensors` + `vocab.txt` format
that `needle-rs` loads:

```bash
# Float32 (~100 MB)
python3 scripts/export.py \
  --checkpoint checkpoints/needle_finetuned_*_best.pkl \
  --output-dir output/

# INT4 quantized (~28 MB, 72% smaller)
python3 scripts/export.py \
  --checkpoint checkpoints/needle_finetuned_*_best.pkl \
  --output-dir output/ \
  --quantize int4
```

### INT4 format

Kernel weights (attention projections, FFN) are group-wise quantized with
`group_size=32`. The `needle-rs` runtime auto-detects prequantized tensors
by the presence of `{name}.scale` companion tensors and dequantizes on-the-fly
with AVX2/NEON SIMD.

## Testing

Evaluate an exported model against a test set:

```bash
# Test the exported .safetensors model (needle-rs runtime)
chrome-ai needletest --model output/needle.safetensors --test data/needle/test.jsonl

# Test the training checkpoint (needle training package)
chrome-ai needletest --checkpoint checkpoints/needle_finetuned_*_best.pkl --test data/needle/test.jsonl
```

Or directly via Python:

```bash
# Training checkpoint
needle eval --checkpoint checkpoints/needle_finetuned_*_best.pkl \
  --test data/needle/test.jsonl

# Exported safetensors
python3 scripts/eval.py --model output/needle.safetensors \
  --test data/needle/test.jsonl
```

## Comparison

Compare Needle routing against Gemini Nano routing on the same test set.
Requires the chrome-ai bridge running (`python3 server.py` + bridge page open in Chrome):

```bash
chrome-ai compare \
  --needle-model output/needle.safetensors \
  --test data/needle/test.jsonl
```

This routes each test query through both Needle (via `needle_rs`) and Gemini Nano
(via the bridge), then reports accuracy for each.

## Publishing

The exported `needle.safetensors` + `vocab.txt` can be hosted anywhere
downloadable by `needle-rs` at runtime (CDN, Hugging Face, GitHub releases).

A reference model for bside's CORE_TOOLS_ROUTING is published at:
[TBD — Hugging Face repo or CDN URL]