---
name: chrome-ai
description: Call Chrome's built-in AI APIs (Prompt, Summarizer, Translator, Writer) from Node.js or test scripts. Use when the user needs to test Chrome's LanguageModel/Prompt API, benchmark Gemini Nano, or integrate Chrome AI APIs into automated pipelines. Triggers include "test Chrome Prompt API", "benchmark Gemini Nano", "test LanguageModel API", "call Chrome AI from Node.js", "access Chrome built-in AI", or any task requiring programmatic access to Chrome's on-device AI.
allowed-tools: Bash(node:*)
---

> This repo is also an npm package: `npm install chrome-ai` → `import { prompt } from 'chrome-ai'`.

# Chrome AI — Node.js client for Chrome's built-in AI

Chrome's built-in AI APIs (Gemini Nano) only run inside Chrome pages — no CLI, no REST API, no native binding. chrome-ai bridges that gap with a local HTTP server and a bridge page the user opens once in Chrome.

## How it works

```
Node.js: prompt({ system, user })
    │
    ├─ POST /prompt → server queue
    │
    ▼
Bridge page (Chrome, open once):
    - polls /pending every 500ms
    - calls LanguageModel.create() + session.prompt()
    - POSTs result to /result/{id}
    │
    ▼
Node.js: poll /result/{id} → return result
```

## Usage (npm)

```bash
npm install chrome-ai
```

```js
import { prompt } from 'chrome-ai';

// On first call, chrome-ai prints the bridge URL to stderr.
// Open that URL in Chrome once and keep the tab open.
const answer = await prompt({
  system: 'You are a helpful assistant.',
  user: 'What is the capital of France?',
});
console.log(answer);
```

## Usage (manual, from any language)

The server pattern works from any language that can make HTTP requests:

```python
import requests, time

# Start the bridge (or open http://localhost:8765 in Chrome)
# Submit a prompt
r = requests.post('http://localhost:8765/prompt', json={
    'system': 'You are helpful.',
    'user': 'Hello!'
})
prompt_id = r.json()['id']

# Poll for result
while True:
    r = requests.get(f'http://localhost:8765/result/{prompt_id}')
    if r.status_code == 200:
        print(r.json()['text'])
        break
    time.sleep(1)
```

## Bridge Page

The server serves a bridge page at the root URL. Open it in Chrome once:

```
Chrome AI Bridge
Ready (available)

Prompt abc123...
  OK (42 chars)
```

Shows connection status, processes pending prompts automatically, and displays a log. Keep this tab open while using the API.

## API

### `prompt(opts)`

| Option | Type | Default |
|--------|------|---------|
| `system` | string | `''` |
| `user` | string | *required* |

Returns a Promise that resolves when Chrome processes the prompt.

### `summarize(opts)`, `translate(opts)`, `write(opts)`

Coming soon — same bridge pattern, dispatches to the right Chrome AI API in the page.

## Requirements

- Recent desktop Chrome (v129+, Prompt API on by default)
- No agent-browser needed. No extensions needed. Just Chrome.

## Server Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/prompt` | Submit a prompt `{system, user}` → `{id}` |
| GET | `/pending` | Bridge page polls this for pending prompts |
| POST | `/result/{id}` | Bridge page submits results `{status, text}` |
| GET | `/result/{id}` | Client polls this for the result |
| GET | `/health` | Health check `{ok, port, pending}` |
