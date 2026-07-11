# Chrome AI

Call Chrome's built-in AI APIs (Gemini Nano) from Node.js.

Chrome's AI APIs only run inside browser pages — no CLI, no REST API. chrome-ai bridges that gap: a local HTTP server + a bridge page you open once in Chrome.

## Install

```bash
npm install chrome-ai
```

No other dependencies. Just Chrome.

## Usage

```js
import { prompt } from 'chrome-ai';

// First call prints the bridge URL to stderr.
// Open that URL in Chrome and keep the tab open.

const answer = await prompt({
  system: 'You are helpful.',
  user: 'What is the capital of France?',
});
console.log(answer); // "Paris."
```

## How it works

```
Node.js                 Server (localhost)        Chrome (bridge page)
  │                         │                         │
  ├─ POST /prompt ─────────▶│                         │
  │                         │◀── GET /pending ────────┤ (polls every 500ms)
  │                         │── [{id, system, user}]─▶│
  │                         │                         │ calls LanguageModel API
  │                         │◀── POST /result/{id} ───┤
  │◀─ GET /result/{id} ────│                         │
  │                         │                         │
```

## API

### `prompt(opts)`

| Option | Type | Default |
|--------|------|---------|
| `system` | string | `''` |
| `user` | string | *required* |

More APIs (summarize, translate, write) coming soon.

## Also a Pi Skill

This repo contains a [SKILL.md](SKILL.md) for use with [Pi coding agent](https://github.com/earendil-works/pi-coding-agent):

```bash
skills.sh install donpark/chrome-ai
```
