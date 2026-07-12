// chrome-ai TypeScript client — thin HTTP wrapper around the Python server.
// The server must be running: python chrome_ai/server.py
// Or set CHROME_AI_URL env var to point to a running server.
let _base = '';
function base() {
    if (_base)
        return _base;
    _base = process.env.CHROME_AI_URL ?? 'http://localhost:0';
    if (_base.endsWith('/'))
        _base = _base.slice(0, -1);
    return _base;
}
async function submitPrompt(system, user) {
    const resp = await fetch(`${base()}/prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system, user }),
    });
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
    throw new Error(`Prompt ${id} timed out after ${timeoutMs}ms`);
}
export async function prompt(opts) {
    const id = await submitPrompt(opts.system ?? '', opts.user);
    console.error(`Chrome AI: prompt ${id} submitted. Bridge page: ${base()}`);
    return waitForResult(id);
}
