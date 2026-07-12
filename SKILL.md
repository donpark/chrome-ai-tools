---
name: chrome-ai
description: Call Chrome's built-in AI APIs (Prompt, Summarizer, Translator, Writer) from Python or Node.js. Use when the user needs to test Chrome's LanguageModel/Prompt API, benchmark Gemini Nano, or integrate Chrome AI APIs into test pipelines. Triggers include "test Chrome Prompt API", "benchmark Gemini Nano", "test LanguageModel API", "call Chrome AI from Python", or any task requiring programmatic access to Chrome's on-device AI.
allowed-tools: Bash(node:*), Bash(python3:*)
---

> **Status: Alpha. Not yet published to npm.**
> npm: `npm install chrome-ai` → `import { prompt, summarize, translate, write } from 'chrome-ai'`
> Python: `python chrome_ai/server.py` then `from chrome_ai.client import prompt, summarize, translate, write`
> CLI: `chrome-ai prompt|summarize|translate|write [opts] [text]`

# Chrome AI — Python server + dual language bindings + CLI

Chrome's built-in AI APIs (Gemini Nano) only run inside Chrome pages. chrome-ai bridges that gap: a Python HTTP server manages a prompt queue, and a bridge page opened once in Chrome processes prompts via **LanguageModel**, **Summarizer**, **Translator**, and **Writer** APIs.

## Architecture

```
Client → POST /prompt {api, ...params} → Python server queue → Bridge page (Chrome) → dispatches to correct API → POST /result → Client polls
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
npx chrome-ai translate --from en --to fr "Hello"
npx chrome-ai write "Write a poem about cats"
cat some-file.txt | npx chrome-ai summarize
```

**4. Or use from Python:**

```python
from chrome_ai.client import prompt, summarize, translate, write

text = prompt("You are helpful.", "Hello!")
summary = summarize("Long text...")
french = translate("Hello", "en", "fr")
poem = write("Write a haiku")
```

**5. Or from Node.js:**

```js
import { prompt, summarize, translate, write } from 'chrome-ai';

const text = await prompt({ system: 'You are helpful.', user: 'Hello!' });
const summary = await summarize('Long text...');
const french = await translate('Hello', 'en', 'fr');
const poem = await write('Write a haiku');
```

**6. Or from curl:**

```bash
# Prompt API
curl -s -X POST http://localhost:62835/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"prompt","system":"You are helpful.","user":"Hello!"}'

# Summarizer API
curl -s -X POST http://localhost:62835/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"summarize","text":"Long text..."}'

# Translator API
curl -s -X POST http://localhost:62835/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"translate","text":"Hello","sourceLanguage":"en","targetLanguage":"fr"}'

# Writer API
curl -s -X POST http://localhost:62835/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"write","text":"Write a haiku","context":"dogs"}'

# Poll
curl -s http://localhost:62835/result/abc123
# → {"status": "done", "text": "..."}
```

## API Reference

### Python Client

```python
from chrome_ai.client import prompt, summarize, translate, write

# Prompt API
prompt(system: str, user: str, timeout: float = 120) -> str

# Summarizer API
summarize(text: str, timeout: float = 120) -> str

# Translator API
translate(text: str, source_language: str, target_language: str, timeout: float = 120) -> str

# Writer API
write(text: str, context: str = "", timeout: float = 120) -> str
```

The client auto-starts the server if not already running.

### TypeScript Client

```ts
import { prompt, summarize, translate, write } from 'chrome-ai';

prompt(opts: { system?: string; user: string }): Promise<string>
summarize(text: string): Promise<string>
translate(text: string, sourceLanguage: string, targetLanguage: string): Promise<string>
write(text: string, context?: string): Promise<string>
```

Requires the server to be running (or `CHROME_AI_URL` env var set).

### CLI

```bash
# Prompt
chrome-ai prompt "What is the capital of France?"

# Summarize
chrome-ai summarize "Some text to summarize..."

# Translate (--from defaults to en if omitted)
chrome-ai translate --from en --to fr "Hello world"
echo "Hello" | chrome-ai translate --from en --to es

# Write
chrome-ai write "Write a poem about cats"
chrome-ai write "Write a story" --context "space pirates"

# Pipe text
cat file.txt | chrome-ai summarize
```

Auto-starts the Python server if not already running.

### HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/prompt` | Submit job `{api, ...params}` → `{id}` |
| GET | `/pending` | Bridge page polls for pending jobs |
| POST | `/result/{id}` | Bridge page submits `{status, text}` |
| GET | `/result/{id}` | Client polls for result |
| GET | `/health` | `{ok, port, pending}` |

POST `/prompt` params by API:

| api | Required | Optional |
|-----|----------|----------|
| `prompt` | `user` | `system` |
| `summarize` | `text` | — |
| `translate` | `text`, `sourceLanguage`, `targetLanguage` | — |
| `write` | `text` | `context` |

## Requirements

- Recent desktop Chrome (v129+)
- Python 3.9+ (for the server)
- Node.js (for the TypeScript client and CLI)
