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
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

_pending: dict[str, dict] = {}
_results: dict[str, dict] = {}
_lock = threading.Lock()
_port = 0

BRIDGE_PAGE = """<!DOCTYPE html>
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
let serverDown = false;

function log(msg) {
  const el = document.getElementById('log');
  el.textContent += msg + '\\n';
  el.scrollTop = el.scrollHeight;
}

async function checkAPI() {
  const el = document.getElementById('status');
  const api = globalThis.LanguageModel;
  if (!api) { el.className = 'err'; el.textContent = 'LanguageModel not available.'; return false; }
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
    if (!resp.ok) throw new Error(String(resp.status));
    const jobs = await resp.json();
    if (serverDown) { serverDown = false; checkAPI(); }
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
        }).catch(() => {});
      }
    }
  } catch(e) {
    if (!serverDown) {
      serverDown = true;
      document.getElementById('status').className = 'status';
      document.getElementById('status').textContent = 'Server offline, retrying...';
    }
  }
}

checkAPI().then(ok => { if (ok) setInterval(poll, POLL_MS); });
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html, status=200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            return self._html(BRIDGE_PAGE)

        if path == "/health":
            with _lock:
                return self._json({"ok": True, "port": _port, "pending": len(_pending)})

        if path == "/pending":
            with _lock:
                jobs = [
                    {"id": pid, "system": p["system"], "user": p["user"]}
                    for pid, p in _pending.items()
                ]
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

        if path == "/prompt":
            prompt_id = uuid.uuid4().hex[:12]
            with _lock:
                _pending[prompt_id] = {
                    "system": body.get("system", ""),
                    "user": body.get("user", ""),
                }
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
    server = HTTPServer(("localhost", port), _Handler)
    _port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return _port


def main():
    port = start_server()
    print(f"http://localhost:{port}")
    sys.stdout.flush()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
