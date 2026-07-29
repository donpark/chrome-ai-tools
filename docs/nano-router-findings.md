# Gemini Nano as a Tool Router: Findings

**Testbed:** Chrome Prompt API (Gemini Nano ~3B) via chrome-ai-tools `agentRoute()` bridge
**Task:** Route user intents to 6 tools (summarize, lookup, create post, vet YouTube, list agents, get page context)
**Dataset:** 259 synthetic queries — ~30 per tool + 40 unsupported (should return null) + 40 ambiguous
**Caveats:** Single Chrome instance, single Nano model version. Synthetic queries typed by evaluator, not real user traffic.

---

## What worked

- **100% JSON parse rate** with compact DSL prompts (not verbose JSON Schema)
- **88.8% tool accuracy** on direct tool queries — solid for a ~3B on-device model
- **96.7%** on `list_matching_agents` — obvious tool mappings work well
- **93.1% structural arg correctness** — when tool is correct, required keys are present

## What broke

- **27.5% rejection rate on unsupported queries** — Nano almost never returns null. "Schedule a meeting" → routed to `get_page_context`. "How tall is the Eiffel Tower?" → routed to `summarize_page`. A primary router that routes everything is unsafe for autonomous agents.
- **73.3% `vet_youtube` accuracy** — confuses channel analysis with post lookup or generic page tools
- **GEPA self-improvement (6 gen):** 3 gen with Nano + 3 gen with DeepSeek V4 Pro — zero improvement. Nano produces identical prompts when asked to self-debug. DeepSeek V4 Pro generated better prompts but Nano ignores the abstention instruction. The abstention gap is a model capability ceiling, not a prompt issue.
- **Evaluation limitation:** Required args (`create_post.body`, `vet_youtube.channel_url`) are defined as user-provided in schemas but the prompt says executor fills them from context. Benchmark marks bare queries like "Post my comment" as correct routing, mixing tool selection accuracy with argument recovery — a contract decision that should be resolved before training a dedicated router.

## Verdict

| Use case | Viable? | Why |
|----------|---------|-----|
| Primary router in autonomous agent | ❌ | 72.5% false-positive rejection rate will route unsupported input to wrong tools |
| Safety fallback (Needle null → Nano) | ❌ | Nano's failure mode is force-routing everything — the opposite of what a fallback needs |
| Dev prototyping / smoke tests | ✅ | 88% accuracy is useful for quick validation before training a dedicated router |

## Key lesson

**Small on-device language models need a dedicated router.** A ~3B generalist LM can route clear intents but lacks the abstention reasoning a production agent requires. Needle (26M parameters, purpose-trained for tool routing) is the right choice — smaller footprint, deterministic output, and trainable on your tool set.

For anyone building on this: if you're using chrome-ai-tools `agentRoute()` for prototyping, the bridge works well. But don't ship it as your primary router — use it to validate tool schemas and collect training data for a dedicated model.
