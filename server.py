#!/usr/bin/env python3
"""
chrome-ai server — HTTP bridge between test scripts and Chrome's built-in AI APIs.

Start once, keep running. Opens no browser — the user opens the bridge page
in Chrome manually.

Usage:
  python chrome_ai/server.py
  # Prints bridge URL, then waits for prompts.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

DEFAULT_PORT = 8462

_pending: dict[str, dict] = {}
_results: dict[str, dict] = {}
_api_status: dict[str, str] = {}
_lock = threading.Lock()
_port = 0

BRIDGE_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chrome AI Bridge</title>
<style>
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --muted: #8b949e;
    --accent: #58a6ff;
    --green: #3fb950;
    --red: #f85149;
    --yellow: #d2991d;
    --purple: #a371f7;
    --orange: #d1865e;
    --font: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    --radius: 6px;
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;overflow:hidden}
  body{
    font:13px/1.5 var(--font);
    background:var(--bg);
    color:var(--text);
    display:flex;flex-direction:column;
  }

  /* ── header ── */
  header{
    flex-shrink:0;
    display:flex;align-items:center;gap:12px;
    padding:10px 16px;
    background:var(--surface);
    border-bottom:1px solid var(--border);
  }
  header h1{font-size:13px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;color:var(--accent)}
  .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
  .dot.online{background:var(--green);box-shadow:0 0 6px var(--green)}
  .dot.offline{background:var(--red)}
  .dot.pending{background:var(--yellow);animation:pulse 1s infinite}
  .spacer{flex:1}
  .stats{font-size:11px;color:var(--muted);display:flex;gap:16px}
  .stats b{color:var(--text)}

  /* ── api status chips ── */
  #apibar{
    flex-shrink:0;
    display:flex;gap:8px;padding:6px 16px;
    background:var(--surface);
    border-bottom:1px solid var(--border);
  }
  .chip{
    font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.3px;
    padding:3px 8px;border-radius:3px;
    border:1px solid var(--border);
    color:var(--muted);
    transition:all .2s;
  }
  .chip.ready{border-color:var(--green);color:var(--green)}
  .chip.down{border-color:var(--red);color:var(--red)}
  .chip.after{border-color:var(--yellow);color:var(--yellow)}

  /* ── job list ── */
  main{
    flex:1;overflow-y:auto;overflow-x:hidden;
    padding:12px 16px;
    display:flex;flex-direction:column;gap:10px;
    scroll-behavior:smooth;
  }
  main:empty::after{
    content:'Waiting for jobs...';
    display:block;text-align:center;color:var(--muted);
    padding:60px 0;font-size:13px;
  }

  /* ── job card ── */
  .card{
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:var(--radius);
    overflow:hidden;
    animation:slideIn .25s ease-out;
  }
  .card-head{
    display:flex;align-items:center;gap:8px;
    padding:8px 12px;
    cursor:pointer;
    user-select:none;
    border-bottom:1px solid transparent;
    transition:background .15s;
  }
  .card-head:hover{background:rgba(255,255,255,.03)}
  .card.open .card-head{border-bottom-color:var(--border)}
  .card-badge{
    font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;
    padding:2px 7px;border-radius:3px;
  }
  .badge-prompt{background:rgba(88,166,255,.15);color:var(--accent)}
  .badge-summarize{background:rgba(163,113,247,.15);color:var(--purple)}
  .badge-translate{background:rgba(210,153,29,.15);color:var(--yellow)}
  .badge-write{background:rgba(209,134,94,.15);color:var(--orange)}
  .card-id{font-size:10px;color:var(--muted)}
  .card-state{font-size:10px;margin-left:auto}
  .state-running{color:var(--yellow)}
  .state-done{color:var(--green)}
  .state-error{color:var(--red)}
  .chevron{font-size:10px;color:var(--muted);transition:transform .2s}
  .card.open .chevron{transform:rotate(90deg)}

  .card-body{display:none;padding:12px}
  .card.open .card-body{display:block}
  .kv{margin-bottom:8px}
  .kv:last-child{margin-bottom:0}
  .kv-key{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);margin-bottom:4px}
  .kv-val{
    font-size:12px;line-height:1.6;
    white-space:pre-wrap;word-break:break-word;
    background:var(--bg);
    padding:8px 10px;border-radius:4px;
    max-height:400px;overflow-y:auto;
  }
  .kv-val.error{color:var(--red);border-left:2px solid var(--red)}
  .kv-val.success{border-left:2px solid var(--green)}

  /* ── empty state ── */
  .empty{
    text-align:center;padding:60px 0;color:var(--muted);
  }
  .empty-icon{font-size:32px;margin-bottom:10px;opacity:.4}

  /* ── animations ── */
  @keyframes slideIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

  /* ── scrollbar ── */
  ::-webkit-scrollbar{width:6px;height:6px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>
<header>
  <div class="dot offline" id="dot"></div>
  <h1>Chrome AI Bridge</h1>
  <div class="spacer"></div>
  <div class="stats">
    <span>Jobs: <b id="jobCount">0</b></span>
    <span>Done: <b id="doneCount">0</b></span>
    <span>Errors: <b id="errCount">0</b></span>
    <span>Uptime: <b id="uptime">--</b></span>
  </div>
</header>
<div id="apibar">
  <span class="chip" id="chip-prompt">prompt</span>
  <span class="chip" id="chip-summarizer">summarizer</span>
  <span class="chip" id="chip-translator">translator</span>
  <span class="chip" id="chip-writer">writer</span>
</div>
<main id="jobs"></main>
<script>
const POLL_MS = 500;
let processed = new Set();
let jobs = {};
let serverDown = false;
let startTime = Date.now();
let jobCount = 0, doneCount = 0, errCount = 0;

const $jobs = document.getElementById('jobs');
const $dot = document.getElementById('dot');

function el(tag, attrs, ...children) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (k === 'cls') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(typeof c === 'string' ? document.createTextNode(c) : c);
  return e;
}

function setChip(id, status) {
  const c = document.getElementById('chip-' + id);
  c.classList.remove('ready','down','after');
  if (status === 'readily') c.classList.add('ready');
  else if (status === 'unavailable' || String(status).startsWith('error')) c.classList.add('down');
  else c.classList.add('after');
  c.title = id + ': ' + status;
}

function badgeClass(api) {
  return {prompt:'badge-prompt',summarize:'badge-summarize',translate:'badge-translate',write:'badge-write'}[api] || 'badge-prompt';
}

function stateClass(status) {
  return {running:'state-running',done:'state-done',error:'state-error'}[status] || '';
}

function updateJobCard(id, updates) {
  const j = jobs[id];
  if (!j) return;
  Object.assign(j, updates);
  const card = j.el;
  // update state badge
  const stateEl = card.querySelector('.card-state');
  stateEl.textContent = j.status;
  stateEl.className = 'card-state ' + stateClass(j.status);
  // update body if open
  const body = card.querySelector('.card-body');
  if (card.classList.contains('open')) {
    body.innerHTML = '';
    renderBody(j, body);
  }
}

function renderBody(j, body) {
  // Input params
  for (const [k, v] of Object.entries(j.params || {})) {
    if (!v) continue;
    body.append(
      el('div', {cls:'kv'},
        el('div', {cls:'kv-key'}, k),
        el('div', {cls:'kv-val',title:k}, v)
      )
    );
  }
  // Response
  if (j.response != null) {
    const cls = j.status === 'error' ? 'kv-val error' : 'kv-val success';
    body.append(
      el('div', {cls:'kv'},
        el('div', {cls:'kv-key'}, 'response (' + j.response.length + ' chars)'),
        el('div', {cls}, j.response)
      )
    );
  }
}

function addJob(id, api, params) {
  jobCount++;
  document.getElementById('jobCount').textContent = jobCount;
  const j = {id, api, params, status:'running', response:null, ts:Date.now()};
  jobs[id] = j;

  const card = el('div', {cls:'card open'});
  card.addEventListener('click', function(e) {
    if (e.target.closest('.kv-val')) return;
    card.classList.toggle('open');
  });
  j.el = card;

  const head = el('div', {cls:'card-head'},
    el('span', {cls:'card-badge ' + badgeClass(api)}, api),
    el('span', {cls:'card-id'}, id),
    el('span', {cls:'card-state ' + stateClass('running')}, 'running'),
    el('span', {cls:'chevron'}, '\u25b6')
  );
  const body = el('div', {cls:'card-body'});
  renderBody(j, body);
  card.append(head, body);
  $jobs.prepend(card);
}

function updateStats() {
  document.getElementById('doneCount').textContent = doneCount;
  document.getElementById('errCount').textContent = errCount;
  const s = Math.floor((Date.now() - startTime) / 1000);
  const m = Math.floor(s / 60);
  document.getElementById('uptime').textContent = m + 'm ' + (s % 60) + 's';
}
setInterval(updateStats, 1000);

async function checkAPI() {
  const api = globalThis.LanguageModel;
  if (!api) {
    $dot.className = 'dot offline';
    return false;
  }
  const results = {};
  try {
    results.prompt = await api.availability({expectedInputs:[{type:'text',languages:['en']}],expectedOutputs:[{type:'text',languages:['en']}]});
  } catch(e) { results.prompt = 'error: ' + e.message; }
  if (globalThis.Summarizer) {
    try {
      results.summarizer = await globalThis.Summarizer.availability({expectedInputLanguages:['en'],outputLanguage:'en'});
    } catch(e) { results.summarizer = 'error: ' + e.message; }
  }
  if (globalThis.Translator) {
    try {
      results.translator = await globalThis.Translator.availability({sourceLanguage:'en',targetLanguage:'es'});
    } catch(e) { results.translator = 'error: ' + e.message; }
  }
  if (globalThis.Writer) {
    try {
      results.writer = await globalThis.Writer.availability({expectedInputLanguages:['en'],outputLanguage:'en'});
    } catch(e) { results.writer = 'error: ' + e.message; }
  }
  fetch('/api-status', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(results)}).catch(()=>{});

  setChip('prompt', results.prompt || 'unavailable');
  setChip('summarizer', results.summarizer || 'unavailable');
  setChip('translator', results.translator || 'unavailable');
  setChip('writer', results.writer || 'unavailable');

  const ok = results.prompt !== 'unavailable' && !String(results.prompt).startsWith('error');
  if (ok && !serverDown) $dot.className = 'dot online';
  return ok;
}

async function waitReady(api, name) {
  while (true) {
    try {
      const avail = await api.availability({expectedInputs:[{type:'text',languages:['en']}],expectedOutputs:[{type:'text',languages:['en']}]});
      if (avail === 'unavailable') throw new Error(name + ' not available');
      if (avail === 'readily') return;
    } catch(e) {}
    await new Promise(r => setTimeout(r, 2000));
  }
}

async function processJob(job) {
  if (job.api === 'summarize') {
    const s = await globalThis.Summarizer.create({expectedInputLanguages:['en'],outputLanguage:'en'});
    try { return await s.summarize(job.text); } finally { s.destroy(); }
  }
  if (job.api === 'translate') {
    const t = await globalThis.Translator.create({sourceLanguage:job.sourceLanguage,targetLanguage:job.targetLanguage});
    try { return await t.translate(job.text); } finally { t.destroy(); }
  }
  if (job.api === 'write') {
    if (!globalThis.Writer) throw new Error('Writer API not available');
    const w = await globalThis.Writer.create({expectedInputLanguages:['en'],outputLanguage:'en'});
    const opts = job.context ? {context:job.context} : undefined;
    try { return await w.write(job.text, opts); } finally { w.destroy(); }
  }
  const session = await globalThis.LanguageModel.create({
    initialPrompts: job.system ? [{role:'system',content:job.system}] : [],
    expectedInputs:[{type:'text',languages:['en']}],
    expectedOutputs:[{type:'text',languages:['en']}],
  });
  try { return await session.prompt(job.user || ''); } finally { if (session.destroy) session.destroy(); }
}

async function poll() {
  try {
    const resp = await fetch('/pending');
    if (!resp.ok) throw new Error(String(resp.status));
    const incoming = await resp.json();
    if (serverDown) { serverDown = false; checkAPI(); }
    for (const job of incoming) {
      if (processed.has(job.id)) continue;
      processed.add(job.id);
      // Build params object
      const params = {};
      for (const [k,v] of Object.entries(job)) {
        if (k === 'id' || k === 'api') continue;
        params[k] = v;
      }
      addJob(job.id, job.api, params);
      try {
        const text = await processJob(job);
        updateJobCard(job.id, {status:'done', response:text});
        doneCount++;
        await fetch('/result/' + job.id, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'done',text})});
      } catch(e) {
        const msg = e.message || '';
        if (msg.includes('downloading') || msg.includes('downloadable') || msg.includes('user gesture')) {
          processed.delete(job.id);
          delete jobs[job.id];
          if (jobs[job.id]?.el) jobs[job.id].el.remove();
          jobCount--;
        } else {
          updateJobCard(job.id, {status:'error', response:msg});
          errCount++;
          await fetch('/result/' + job.id, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:'error',error:msg})}).catch(()=>{});
        }
      }
    }
  } catch(e) {
    if (!serverDown) {
      serverDown = true;
      $dot.className = 'dot pending';
    }
  }
}

checkAPI().then(ok => { if (ok) setInterval(poll, POLL_MS); });
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html, status=200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            return self._html(BRIDGE_PAGE)

        if path == "/health":
            with _lock:
                return self._json({"ok": True, "port": _port, "pending": len(_pending)})

        if path == "/status":
            with _lock:
                return self._json(dict(_api_status))

        if path == "/pending":
            with _lock:
                jobs = []
                for pid, p in _pending.items():
                    job = {"id": pid, "api": p["api"]}
                    for k, v in p.items():
                        if k != "api":
                            job[k] = v
                    jobs.append(job)
            return self._json(jobs)

        if path.startswith("/result/"):
            prompt_id = path.split("/")[-1]
            with _lock:
                if prompt_id in _results:
                    data = _results.pop(prompt_id)
                    return self._json(data)
            return self._json({"status": "pending"}, 202)

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        if path == "/api-status":
            with _lock:
                _api_status.clear()
                _api_status.update(body)
            return self._json({"ok": True})

        if path == "/prompt":
            api = body.get("api", "prompt")

            # Reject if bridge has reported and this API is unavailable/missing
            key = {"summarize": "summarizer", "translate": "translator", "write": "writer"}.get(api, "prompt")
            with _lock:
                status = _api_status.get(key)
            if _api_status and status is None:
                return self._json({"error": f"{api} API not available in this Chrome"}, 503)
            if _api_status and (status == "unavailable" or status.startswith("error")):
                return self._json({"error": f"{api} not available (status: {status})"}, 503)

            prompt_id = uuid.uuid4().hex[:12]

            with _lock:
                job: dict[str, str] = {"api": api}
                if api == "prompt":
                    job["system"] = body.get("system", "")
                    job["user"] = body.get("user", "")
                elif api == "summarize":
                    job["text"] = body.get("text", "")
                elif api == "translate":
                    job["text"] = body.get("text", "")
                    job["sourceLanguage"] = body.get("sourceLanguage", "en")
                    job["targetLanguage"] = body.get("targetLanguage", "en")
                elif api == "write":
                    job["text"] = body.get("text", "")
                    job["context"] = body.get("context", "")
                _pending[prompt_id] = job

            return self._json({"id": prompt_id})

        if path.startswith("/result/"):
            prompt_id = path.split("/")[-1]
            with _lock:
                _results[prompt_id] = body
                _pending.pop(prompt_id, None)
            return self._json({"ok": True})

        self.send_response(404)
        self.end_headers()


def start_server(port: int = 0):
    """Start the HTTP server. Returns the actual port."""
    global _port
    server = ThreadingHTTPServer(("localhost", port), _Handler)
    _port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return _port


def main():
    port = int(os.environ.get("CHROME_AI_PORT", DEFAULT_PORT))
    try:
        port = start_server(port)
    except OSError as e:
        print(f"Port {port} unavailable ({e}) — server may already be running.", file=sys.stderr)
        sys.exit(1)
    print(f"http://localhost:{port}")
    sys.stdout.flush()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
