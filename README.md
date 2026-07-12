# Chrome AI

Call Chrome's built-in AI APIs (Gemini Nano) from Node.js or Python.

Chrome's AI APIs only run inside browser pages. chrome-ai bridges that gap: a Python HTTP server manages a prompt queue, and a bridge page (open once in Chrome) processes prompts by calling the API directly.

> **Status: Alpha.** Not yet published to npm. APIs may change, edge cases remain. Works for prototyping via local install.

## Install

```bash
npm install chrome-ai-tools
```

Then use the `chrome-ai` CLI directly:

```bash
npx chrome-ai prompt "hello"
# or install globally
npm install -g chrome-ai-tools
chrome-ai summarize "some text"
```

Just Chrome. No agent-browser, no extensions, no API keys.

## Quick Start

Start the server:

```bash
python3 server.py
# → http://localhost:8462
```

Open that URL in Chrome. Keep the tab open.

Now use the **CLI**:

```bash
npx chrome-ai prompt "What is the capital of France?"
npx chrome-ai summarize "Some long text here..."
npx chrome-ai translate --from en --to fr "Hello"
npx chrome-ai write "Write a poem about cats"
# or pipe text in
cat some-file.txt | npx chrome-ai summarize
```

Or from **Node.js**:

```js
import { prompt, summarize, translate, write } from 'chrome-ai-tools';

const answer = await prompt({
  system: 'You are helpful.',
  user: 'What is the capital of France?',
});
const summary = await summarize('Long text...');
const french = await translate('Hello', 'en', 'fr');
const poem = await write('Write a haiku about dogs');
```

Or from **Python**:

```python
from client import prompt, summarize, translate, write

answer = prompt('You are helpful.', 'What is the capital of France?')
summary = summarize('Long text...')
french = translate('Hello', 'en', 'fr')
poem = write('Write a haiku about dogs')
```

Or from **any HTTP client**:

```bash
# Prompt API
curl -s -X POST http://localhost:8462/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"prompt","system":"You are helpful.","user":"Hello!"}'

# Summarizer API
curl -s -X POST http://localhost:8462/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"summarize","text":"Long text to summarize..."}'

# Translator API
curl -s -X POST http://localhost:8462/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"translate","text":"Hello","sourceLanguage":"en","targetLanguage":"fr"}'

# Writer API
curl -s -X POST http://localhost:8462/prompt \
  -H 'Content-Type: application/json' \
  -d '{"api":"write","text":"Write a haiku","context":"dogs"}'

# Poll for result
curl -s http://localhost:8462/result/a1b2c3d4e5f6
# → {"status": "done", "text": "..."}
```

## How it works

```
Client (Node / Python / curl / CLI)
    │
    ├─ POST /prompt {api, ...params} → {id}
    │
    ▼
Python HTTP server — manages prompt queue
    │
    ├─ GET /pending ← bridge page polls every 500ms
    │
    ▼
Bridge page (Chrome, open once)
    - dispatches to LanguageModel / Summarizer / Translator / Writer
    - POSTs result to /result/{id}
    │
    ▼
Client — poll GET /result/{id} → result
```

## API

### TypeScript

```ts
import { prompt, summarize, translate, write } from 'chrome-ai-tools';

// Prompt API
const text = await prompt({
  system?: string,  // system prompt (optional)
  user: string,     // user message (required)
});

// Summarizer API
const summary = await summarize(text: string);

// Translator API
const translated = await translate(
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
);

// Writer API
const written = await write(text: string, context?: string);
```

### Python

```python
from client import prompt, summarize, translate, write

text = prompt(system: str, user: str, timeout: float = 120)

summary = summarize(text: str, timeout: float = 120)

translated = translate(
    text: str,
    source_language: str,
    target_language: str,
    timeout: float = 120,
)

written = write(text: str, context: str = "", timeout: float = 120)
```

### CLI

```bash
chrome-ai prompt "What is the capital of France?"

chrome-ai summarize "Some text to summarize..."

chrome-ai translate --from en --to fr "Hello world"

chrome-ai write "Write a poem" --context "cats"

# Pipe text in
cat file.txt | chrome-ai summarize
cat file.txt | chrome-ai translate --from en --to es
```

Auto-starts the Python server if not already running.

### Server Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/prompt` | Submit a job `{api, ...params}` → `{id}` |
| GET | `/pending` | Bridge page polls for pending jobs |
| POST | `/result/{id}` | Bridge page submits result `{status, text}` |
| GET | `/result/{id}` | Client polls for result |
| GET | `/health` | `{ok, port, pending}` |

#### POST /prompt params

| api | Required params | Optional params |
|-----|----------------|-----------------|
| `prompt` | `user` | `system` |
| `summarize` | `text` | — |
| `translate` | `text`, `sourceLanguage`, `targetLanguage` | — |
| `write` | `text` | `context` |

## Requirements

- Recent desktop Chrome (v129+, Prompt API on by default)
- Python 3.9+

## Also a Pi Skill

[SKILL.md](SKILL.md) — installable via `skills.sh install donpark/chrome-ai` for use with Pi coding agent.
