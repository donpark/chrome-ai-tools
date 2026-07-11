import { start as startServer, getPort } from './server.js';
// ── internal ──────────────────────────────────────────────────
const BASE = 'http://localhost';
function ensureStarted() {
    return startServer();
}
async function fetchJSON(url, opts) {
    const resp = await fetch(url, opts);
    if (!resp.ok) {
        const body = await resp.text().catch(() => '');
        throw new Error(`${resp.status}: ${body || resp.statusText}`);
    }
    return resp.json();
}
async function submitPrompt(system, user) {
    const data = await fetchJSON(`${BASE}:${getPort()}/prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system, user }),
    });
    return data.id;
}
async function waitForResult(id, timeoutMs = 120_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const data = await fetchJSON(`${BASE}:${getPort()}/result/${id}`);
        if (data.status === 'done')
            return data.text;
        if (data.status === 'error')
            throw new Error(data.error || 'Unknown error');
        // 202 = still pending, poll again
        await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error(`Prompt ${id} timed out after ${timeoutMs}ms`);
}
// ── public API ────────────────────────────────────────────────
let _started = false;
async function lazyStart() {
    if (!_started) {
        await ensureStarted();
        _started = true;
        console.error(`Chrome AI bridge running at ${BASE}:${getPort()}`);
        console.error('Open this URL in Chrome and keep the tab open.');
    }
}
export async function prompt(opts) {
    await lazyStart();
    const id = await submitPrompt(opts.system ?? '', opts.user);
    return waitForResult(id);
}
export async function summarize(_opts) {
    throw new Error('Summarizer not yet implemented via bridge pattern');
}
export async function translate(_opts) {
    throw new Error('Translator not yet implemented via bridge pattern');
}
export async function write(_opts) {
    throw new Error('Writer not yet implemented via bridge pattern');
}
