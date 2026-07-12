---
name: chrome-ai
description: Call Chrome's built-in AI APIs (Prompt, Summarizer, Translator, Writer) from Python or Node.js. Use when the user needs to test Chrome's LanguageModel/Prompt API, benchmark Gemini Nano, or integrate Chrome AI APIs into test pipelines. Triggers include "test Chrome Prompt API", "benchmark Gemini Nano", "test LanguageModel API", "call Chrome AI from Python", or any task requiring programmatic access to Chrome's on-device AI.
allowed-tools: Bash(node:*), Bash(python3:*)
---

> **Status: Alpha. Not yet published to npm.**
> npm: `npm install chrome-ai` → `import { prompt } from 'chrome-ai'`
> Python: `python chrome_ai/server.py` then `from chrome_ai.client import prompt`
> CLI: `npx chrome-ai prompt "hello"` or `chrome-ai summarize "text"` (after `npm install -g`)

# Chrome AI — Python server + dual language bindings + CLI

Chrome's built-in AI APIs (Gemini Nano) only run inside Chrome pages. chrome-ai bridges that gap: a Python HTTP server manages a prompt queue, and a bridge page opened once in Chrome processes prompts.

## Architecture

```
Client → POST /prompt → Python server queue → Bridge page (Chrome) → LanguageModel API → POST /result → Client polls
```

The Python server runs once. The bridge page is a single Chrome tab you keep open. All clients (Python, Node.js, curl, CLI) talk to the same server via HTTP.

## Quick Start

**1. Start the server:**

```bash
python chrome_ai/server.py
# → http://localhost:62835
```

**2. Open that URL in Chrome.** Keep the tab open.

**3. Use the CLI:**

```bash
npx chrome-ai prompt "What is the capital of France?"
npx chrome-ai summarize "Some long text..."
cat some-file.txt | npx chrome-ai summarize
```

**4. Or use from Python:**

```python
from chrome_ai.client import prompt

text = prompt("You are helpful.", "Hello!")
```

**5. Or from Node.js:**

```js
import { prompt } from 'chrome-ai';
const text = await prompt({ system: 'You are helpful.', user: 'Hello!' });
```

**6. Or from curl:**

```bash
curl -s -X POST http://localhost:62835/prompt -H 'Content-Type: application/json' -d '{"system":"You are helpful.","user":"Hello!"}'
# → {"id": "abc123"}
curl -s http://localhost:62835/result/abc123
# → {"status": "done", "text": "Hello!"}
```

## Python Client

```python
prompt(system: str, user: str, timeout: float = 120) -> str
```

The client can auto-start the server if not already running:

```python
from chrome_ai.client import prompt

# First call auto-starts server, opens Chrome bridge page
text = prompt("You are helpful.", "Hello!")
```

## TypeScript Client

```ts
prompt(opts: { system?: string; user: string }): Promise<string>
```

Requires the server to be running (or `CHROME_AI_URL` env var set).

## CLI

```bash
# Direct prompt
chrome-ai prompt "What is the capital of France?"

# Summarize (wraps with system prompt)
chrome-ai summarize "Some text to summarize..."

# Pipe text in
cat long-file.txt | chrome-ai summarize

# Use via npx (no global install)
npx chrome-ai prompt "hello"
```

Auto-starts the Python server if not already running.

## Requirements

- Recent desktop Chrome (v129+)
- Python 3.9+ (for the server)
- Node.js (for the TypeScript client and CLI)
