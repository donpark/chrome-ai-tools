// chrome-ai TypeScript client — thin HTTP wrapper around the Python server.
// The server must be running: python chrome_ai/server.py
// Or set CHROME_AI_URL env var to point to a running server.

export interface PromptOptions {
  system?: string;
  user: string;
}

let _base = '';

function base(): string {
  if (_base) return _base;
  _base = process.env.CHROME_AI_URL ?? 'http://localhost:0';
  if (_base.endsWith('/')) _base = _base.slice(0, -1);
  return _base;
}

async function submitJob(params: Record<string, string>): Promise<string> {
  const resp = await fetch(`${base()}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!resp.ok) throw new Error(`${resp.status}`);
  const data = await resp.json() as { id: string };
  return data.id;
}

async function waitForResult(id: string, timeoutMs = 120_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const resp = await fetch(`${base()}/result/${id}`);
    if (resp.status === 202) {
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (!resp.ok) throw new Error(`${resp.status}`);
    const data = await resp.json() as { status: string; text?: string; error?: string };
    if (data.status === 'done') return data.text!;
    if (data.status === 'error') throw new Error(data.error || 'Unknown error');
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`Job ${id} timed out after ${timeoutMs}ms`);
}

// --- Public API ---

export async function prompt(opts: PromptOptions): Promise<string> {
  const id = await submitJob({ api: 'prompt', system: opts.system ?? '', user: opts.user });
  console.error(`Chrome AI: prompt ${id} submitted. Bridge page: ${base()}`);
  return waitForResult(id);
}

export async function summarize(text: string): Promise<string> {
  const id = await submitJob({ api: 'summarize', text });
  console.error(`Chrome AI: summarize ${id} submitted. Bridge page: ${base()}`);
  return waitForResult(id);
}

export async function translate(
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
): Promise<string> {
  const id = await submitJob({ api: 'translate', text, sourceLanguage, targetLanguage });
  console.error(`Chrome AI: translate ${id} submitted. Bridge page: ${base()}`);
  return waitForResult(id);
}

export async function write(text: string, context?: string): Promise<string> {
  const id = await submitJob({ api: 'write', text, context: context ?? '' });
  console.error(`Chrome AI: write ${id} submitted. Bridge page: ${base()}`);
  return waitForResult(id);
}
