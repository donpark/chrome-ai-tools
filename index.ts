// chrome-ai TypeScript client — thin HTTP wrapper around the Python server.
// The server must be running: python chrome_ai/server.py
// Or set CHROME_AI_URL env var to point to a running server.

export interface PromptOptions {
  system?: string;
  user: string;
}

export const DEFAULT_URL = 'http://localhost:8462';

let _base = '';

function base(): string {
  if (_base) return _base;
  _base = process.env.CHROME_AI_URL ?? DEFAULT_URL;
  if (_base.endsWith('/')) _base = _base.slice(0, -1);
  return _base;
}

async function submitJob(params: Record<string, string>): Promise<string> {
  let resp: Response;
  try {
    resp = await fetch(`${base()}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    throw new Error(
      `chrome-ai server not reachable at ${base()} — run "python3 server.py" and open the bridge page in Chrome, or set CHROME_AI_URL`,
    );
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({error: `${resp.status}`}));
    throw new Error(err.error || `${resp.status}`);
  }
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

// --- Agent Route API ---

import type { ToolDefinition, ToolRoute } from './src/needle-types.js';

export type { ToolDefinition, ToolRoute };

export interface AgentRouteOptions {
  /** Custom system prompt. If omitted, the default compressed DSL prompt is used. */
  system?: string;
}

export async function agentRoute(
  query: string,
  tools: ToolDefinition[],
  opts?: AgentRouteOptions,
): Promise<ToolRoute> {
  const params: Record<string, string> = { api: 'agent-route', query, tools: JSON.stringify(tools) };
  if (opts?.system) params.system = opts.system;
  const id = await submitJob(params);
  const text = await waitForResult(id);
  try {
    return JSON.parse(text);
  } catch {
    return { name: null, arguments: {} };
  }
}

// --- Public API ---

export async function prompt(opts: PromptOptions): Promise<string> {
  const id = await submitJob({ api: 'prompt', system: opts.system ?? '', user: opts.user });
  return waitForResult(id);
}

export async function summarize(text: string): Promise<string> {
  const id = await submitJob({ api: 'summarize', text });
  return waitForResult(id);
}

export async function translate(
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
): Promise<string> {
  const id = await submitJob({ api: 'translate', text, sourceLanguage, targetLanguage });
  return waitForResult(id);
}

export async function write(text: string, context?: string): Promise<string> {
  const id = await submitJob({ api: 'write', text, context: context ?? '' });
  return waitForResult(id);
}

// --- Needle Training Data Generator ---

export { generateTrainingData } from './src/generate.js';

