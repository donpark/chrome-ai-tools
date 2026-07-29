// Tests for chrome-ai TypeScript client and CLI — no AI model needed.

import { describe, it, afterEach, mock, before } from 'node:test';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));

function makeResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('client API', () => {
  afterEach(() => {
    mock.restoreAll();
    delete process.env.CHROME_AI_URL;
  });

  it('prompt() submits and polls', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let callCount = 0;
    mock.method(globalThis, 'fetch', (url: string | URL) => {
      const u = url.toString();
      if (u.endsWith('/prompt')) {
        return Promise.resolve(makeResponse({ id: 'abc123' }, 200));
      }
      callCount++;
      if (callCount === 1) return Promise.resolve(makeResponse({ status: 'pending' }, 202));
      return Promise.resolve(makeResponse({ status: 'done', text: 'Hello world' }, 200));
    });

    const { prompt } = await import('./index.js');
    const result = await prompt({ system: 'sys', user: 'hello' });
    assert.equal(result, 'Hello world');
  });

  it('summarize() sends api=summarize', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let submitted = '';
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt')) {
        submitted = init!.body as string;
        return Promise.resolve(makeResponse({ id: 's1' }, 200));
      }
      return Promise.resolve(makeResponse({ status: 'done', text: 'summary' }, 200));
    });

    const { summarize } = await import('./index.js');
    const result = await summarize('long text here');
    assert.equal(result, 'summary');
    const body = JSON.parse(submitted);
    assert.equal(body.api, 'summarize');
    assert.equal(body.text, 'long text here');
  });

  it('translate() sends api=translate', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let submitted = '';
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt')) {
        submitted = init!.body as string;
        return Promise.resolve(makeResponse({ id: 't1' }, 200));
      }
      return Promise.resolve(makeResponse({ status: 'done', text: 'bonjour' }, 200));
    });

    const { translate } = await import('./index.js');
    const result = await translate('hello', 'en', 'fr');
    assert.equal(result, 'bonjour');
    const body = JSON.parse(submitted);
    assert.equal(body.api, 'translate');
    assert.equal(body.sourceLanguage, 'en');
    assert.equal(body.targetLanguage, 'fr');
  });

  it('write() sends api=write', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let submitted = '';
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt')) {
        submitted = init!.body as string;
        return Promise.resolve(makeResponse({ id: 'w1' }, 200));
      }
      return Promise.resolve(makeResponse({ status: 'done', text: 'poem' }, 200));
    });

    const { write } = await import('./index.js');
    const result = await write('write a poem', 'cats');
    assert.equal(result, 'poem');
    const body = JSON.parse(submitted);
    assert.equal(body.api, 'write');
    assert.equal(body.text, 'write a poem');
    assert.equal(body.context, 'cats');
  });

  it('handles error status', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    mock.method(globalThis, 'fetch', (url: string | URL) => {
      if (url.toString().endsWith('/prompt')) return Promise.resolve(makeResponse({ id: 'err1' }, 200));
      return Promise.resolve(makeResponse({ status: 'error', error: 'model crashed' }, 200));
    });

    const { summarize } = await import('./index.js');
    await assert.rejects(() => summarize('x'), /model crashed/);
  });
});

describe('CLI', () => {
  it('rejects unknown subcommand', async () => {
    const { stderr, code } = await runCLI(['unknown']);
    assert.match(stderr, /Usage:/);
    assert.notEqual(code, 0);
  });

  it('rejects missing text for prompt', async () => {
    const { stderr, code } = await runCLI(['prompt']);
    assert.match(stderr, /No text provided/);
    assert.notEqual(code, 0);
  });

  it('rejects missing text for summarize', async () => {
    const { stderr, code } = await runCLI(['summarize']);
    assert.match(stderr, /No text provided/);
    assert.notEqual(code, 0);
  });

  it('rejects translate without --to', async () => {
    const { stderr, code } = await runCLI(['translate', '--from', 'en', 'hello']);
    assert.match(stderr, /requires --to/);
    assert.notEqual(code, 0);
  });

  it('rejects missing text for translate', async () => {
    const { stderr, code } = await runCLI(['translate', '--from', 'en', '--to', 'fr']);
    assert.match(stderr, /No text provided/);
    assert.notEqual(code, 0);
  });
});

describe('agentRoute', () => {
  afterEach(() => {
    mock.restoreAll();
    delete process.env.CHROME_AI_URL;
  });

  const tools = [
    { name: 'summarize_page', description: 'Summarize page text', inputSchema: { type: 'object', properties: { text: { type: 'string' } } } },
    { name: 'lookup_posts', description: 'Find related posts', inputSchema: { type: 'object', properties: { summary: { type: 'string' } }, required: ['summary'] } },
  ];

  it('submits agent-route job and parses JSON result', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let submitted = '';
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt')) {
        submitted = init!.body as string;
        return Promise.resolve(new Response(JSON.stringify({ id: 'ar1' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ status: 'done', text: '{"name":"summarize_page","arguments":{"text":"page content"}}' }), { status: 200 }));
    });

    const { agentRoute } = await import('./index.js');
    const result = await agentRoute('summarize this page', tools);
    assert.equal(result.name, 'summarize_page');
    assert.deepEqual(result.arguments, { text: 'page content' });

    const body = JSON.parse(submitted);
    assert.equal(body.api, 'agent-route');
    assert.equal(body.query, 'summarize this page');
    assert.ok(body.tools);
    assert.deepEqual(JSON.parse(body.tools), tools);
  });

  it('returns null on JSON parse failure', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt'))
        return Promise.resolve(new Response(JSON.stringify({ id: 'ar2' }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ status: 'done', text: 'not valid json' }), { status: 200 }));
    });

    const { agentRoute } = await import('./index.js');
    const result = await agentRoute('do something', tools);
    assert.equal(result.name, null);
    assert.deepEqual(result.arguments, {});
  });

  it('returns null on empty result', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt'))
        return Promise.resolve(new Response(JSON.stringify({ id: 'ar3' }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ status: 'done', text: '{"name":null,"arguments":{}}' }), { status: 200 }));
    });

    const { agentRoute } = await import('./index.js');
    const result = await agentRoute('what is the weather', tools);
    assert.equal(result.name, null);
  });

  it('passes system prompt override', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let submitted = '';
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const u = url.toString();
      if (u.endsWith('/prompt')) {
        submitted = init!.body as string;
        return Promise.resolve(new Response(JSON.stringify({ id: 'ar4' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ status: 'done', text: '{"name":null,"arguments":{}}' }), { status: 200 }));
    });

    const { agentRoute } = await import('./index.js');
    const custom = 'You are a test router. Be strict.';
    await agentRoute('test query', tools, { system: custom });
    const body = JSON.parse(submitted);
    assert.equal(body.system, custom);
  });
});

function runCLI(args: string[]): Promise<{ stdout: string; stderr: string; code: number }> {
  return new Promise((resolve) => {
    const proc = spawn(
      process.execPath,
      [join(__dirname, 'cli.js'), ...args],
      {
        env: { ...process.env, NODE_OPTIONS: '', CHROME_AI_URL: 'http://localhost:9999' },
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );

    let stdout = '';
    let stderr = '';
    proc.stdout!.on('data', (d: Buffer) => { stdout += d.toString(); });
    proc.stderr!.on('data', (d: Buffer) => { stderr += d.toString(); });

    proc.on('close', (code) => {
      resolve({ stdout, stderr, code: code ?? 0 });
    });
  });
}
