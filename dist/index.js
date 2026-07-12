// chrome-nano TypeScript client — thin HTTP wrapper around the Python server.
// The server must be running: python chrome_ai/server.py
// Or set CHROME_AI_URL env var to point to a running server.
export const DEFAULT_URL = 'http://localhost:8462';
let _base = '';
function base() {
    if (_base)
        return _base;
    _base = process.env.CHROME_AI_URL ?? DEFAULT_URL;
    if (_base.endsWith('/'))
        _base = _base.slice(0, -1);
    return _base;
}
async function submitJob(params) {
    let resp;
    try {
        resp = await fetch(`${base()}/prompt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
    }
    catch {
        throw new Error(`chrome-nano server not reachable at ${base()} — run "python3 server.py" and open the bridge page in Chrome, or set CHROME_AI_URL`);
    }
    if (!resp.ok)
        throw new Error(`${resp.status}`);
    const data = await resp.json();
    return data.id;
}
async function waitForResult(id, timeoutMs = 120_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const resp = await fetch(`${base()}/result/${id}`);
        if (resp.status === 202) {
            await new Promise((r) => setTimeout(r, 1000));
            continue;
        }
        if (!resp.ok)
            throw new Error(`${resp.status}`);
        const data = await resp.json();
        if (data.status === 'done')
            return data.text;
        if (data.status === 'error')
            throw new Error(data.error || 'Unknown error');
        await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error(`Job ${id} timed out after ${timeoutMs}ms`);
}
// --- Public API ---
export async function prompt(opts) {
    const id = await submitJob({ api: 'prompt', system: opts.system ?? '', user: opts.user });
    return waitForResult(id);
}
export async function summarize(text) {
    const id = await submitJob({ api: 'summarize', text });
    return waitForResult(id);
}
export async function translate(text, sourceLanguage, targetLanguage) {
    const id = await submitJob({ api: 'translate', text, sourceLanguage, targetLanguage });
    return waitForResult(id);
}
export async function write(text, context) {
    const id = await submitJob({ api: 'write', text, context: context ?? '' });
    return waitForResult(id);
}
