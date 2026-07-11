import { createServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomBytes } from 'node:crypto';
import type { Server, IncomingMessage, ServerResponse } from 'node:http';

const PAGE_DIR = join(tmpdir(), 'chrome-ai-pages');
mkdirSync(PAGE_DIR, { recursive: true });

// ── state ────────────────────────────────────────────────────

interface PromptJob {
  system: string;
  user: string;
  ts: number;
}

interface PromptResult {
  status: 'done' | 'error';
  text?: string;
  error?: string;
}

const pending = new Map<string, PromptJob>();
const results = new Map<string, PromptResult>();

// ── bridge page ──────────────────────────────────────────────

const BRIDGE_PAGE = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Chrome AI Bridge</title>
<style>body{font:14px system-ui;max-width:600px;margin:40px auto;padding:0 20px}
.ok{color:green}.err{color:red}.status{color:#666}</style></head>
<body>
<h1>Chrome AI Bridge</h1>
<div id="status" class="status">Connecting...</div>
<pre id="log" style="background:#f5f5f5;padding:10px;border-radius:4px;max-height:300px;overflow-y:auto"></pre>
<script>
const POLL_MS = 500;
let processed = new Set();

function log(msg) {
  const el = document.getElementById('log');
  el.textContent += msg + '\\n';
  el.scrollTop = el.scrollHeight;
}

async function checkAPI() {
  const el = document.getElementById('status');
  const api = globalThis.LanguageModel;
  if (!api) { el.className = 'err'; el.textContent = 'LanguageModel not available. Check chrome://flags/#prompt-api-for-gemini-nano'; return false; }
  try {
    const avail = await api.availability({expectedInputs:[{type:'text',languages:['en']}],expectedOutputs:[{type:'text',languages:['en']}]});
    if (avail === 'unavailable') { el.className = 'err'; el.textContent = 'Model not available. Check chrome://components'; return false; }
    el.className = 'ok'; el.textContent = 'Ready (' + avail + ')';
    return true;
  } catch(e) { el.className = 'err'; el.textContent = 'Error: ' + e.message; return false; }
}

async function poll() {
  try {
    const resp = await fetch('/pending');
    const jobs = await resp.json();
    for (const job of jobs) {
      if (processed.has(job.id)) continue;
      processed.add(job.id);
      log('Prompt ' + job.id + '...');
      try {
        const api = globalThis.LanguageModel;
        const session = await api.create({
          initialPrompts: [{role:'system', content: job.system}],
          expectedInputs: [{type:'text',languages:['en']}],
          expectedOutputs: [{type:'text',languages:['en']}],
        });
        try {
          const text = await session.prompt(job.user);
          log('  OK (' + text.length + ' chars)');
          await fetch('/result/' + job.id, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: 'done', text})
          });
        } finally { if (session.destroy) session.destroy(); }
      } catch(e) {
        log('  ERROR: ' + e.message);
        await fetch('/result/' + job.id, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({status: 'error', error: e.message})
        });
      }
    }
  } catch(e) { log('Poll error: ' + e.message); }
}

checkAPI().then(ok => { if (ok) setInterval(poll, POLL_MS); });
</script></body></html>`;

// ── server ───────────────────────────────────────────────────

let port = 0;
let server: Server | null = null;

function json(res: ServerResponse, data: unknown, status = 200) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

export function getPort(): number {
  return port;
}

export function start(): Promise<number> {
  if (server) return Promise.resolve(port);
  return new Promise((resolve) => {
    server = createServer((req, res) => {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      // CORS preflight
      if (method === 'OPTIONS') {
        res.writeHead(204, {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        });
        res.end();
        return;
      }

      // Bridge page
      if (method === 'GET' && (url === '/' || url === '/index.html')) {
        const body = BRIDGE_PAGE;
        res.writeHead(200, {
          'Content-Type': 'text/html; charset=utf-8',
          'Content-Length': Buffer.byteLength(body),
        });
        res.end(body);
        return;
      }

      // Submit a prompt
      if (method === 'POST' && url === '/prompt') {
        let body = '';
        req.on('data', (chunk) => { body += chunk; });
        req.on('end', () => {
          try {
            const { system, user } = JSON.parse(body);
            const id = randomBytes(4).toString('hex');
            pending.set(id, { system: system ?? '', user, ts: Date.now() });
            json(res, { id });
          } catch {
            json(res, { error: 'Bad JSON' }, 400);
          }
        });
        return;
      }

      // Get pending prompts (bridge page polls this)
      if (method === 'GET' && url === '/pending') {
        const jobs = Array.from(pending.entries()).map(([id, job]) => ({
          id, system: job.system, user: job.user,
        }));
        json(res, jobs);
        return;
      }

      // Submit a result (bridge page POSTs here) or check a result (client GETs)
      if (url.startsWith('/result/')) {
        const id = url.slice(8);
        if (method === 'POST') {
          let body = '';
          req.on('data', (chunk) => { body += chunk; });
          req.on('end', () => {
            try {
              const result: PromptResult = JSON.parse(body);
              results.set(id, result);
              pending.delete(id);
              json(res, { ok: true });
            } catch {
              json(res, { error: 'Bad JSON' }, 400);
            }
          });
        } else {
          const result = results.get(id);
          if (result) {
            results.delete(id);
            json(res, result);
          } else {
            json(res, { status: 'pending' }, 202);
          }
        }
        return;
      }

      // Health check
      if (method === 'GET' && url === '/health') {
        json(res, { ok: true, port, pending: pending.size });
        return;
      }

      res.writeHead(404);
      res.end();
    });

    server.listen(0, () => {
      port = (server!.address() as { port: number }).port;
      resolve(port);
    });
  });
}
