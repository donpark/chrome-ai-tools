// Tests for chrome-ai TypeScript client and CLI — no AI model needed.

import { describe, it, afterEach, mock } from 'node:test';
import assert from 'node:assert';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));

function makeResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('prompt()', () => {
  afterEach(() => {
    mock.restoreAll();
    delete process.env.CHROME_AI_URL;
  });

  it('submits prompt and polls for result', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let callCount = 0;
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.endsWith('/prompt')) {
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

  it('handles error status', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    mock.method(globalThis, 'fetch', (url: string | URL) => {
      const urlStr = url.toString();
      if (urlStr.endsWith('/prompt')) return Promise.resolve(makeResponse({ id: 'err1' }, 200));
      return Promise.resolve(makeResponse({ status: 'error', error: 'model crashed' }, 200));
    });

    const { prompt } = await import('./index.js');
    await assert.rejects(() => prompt({ user: 'x' }), /model crashed/);
  });

  it('handles non-200 submit response', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    mock.method(globalThis, 'fetch', () => {
      return Promise.resolve(makeResponse({}, 500));
    });

    const { prompt } = await import('./index.js');
    await assert.rejects(() => prompt({ user: 'x' }), /500/);
  });

  it('defaults to empty system prompt', async () => {
    process.env.CHROME_AI_URL = 'http://localhost:9999';

    let submitted = '';
    mock.method(globalThis, 'fetch', (url: string | URL, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.endsWith('/prompt')) {
        submitted = init!.body as string;
        return Promise.resolve(makeResponse({ id: 'x' }, 200));
      }
      return Promise.resolve(makeResponse({ status: 'done', text: 'ok' }, 200));
    });

    const { prompt } = await import('./index.js');
    await prompt({ user: 'x' });
    const parsed = JSON.parse(submitted);
    assert.equal(parsed.system, '');
    assert.equal(parsed.user, 'x');
  });
});

describe('CLI', () => {
  it('rejects unknown subcommand', async () => {
    const { stderr, code } = await runCLI(['unknown']);
    assert.match(stderr, /Usage:/);
    assert.notEqual(code, 0);
  });

  it('rejects missing text', async () => {
    const { stderr, code } = await runCLI(['prompt']);
    assert.match(stderr, /No text provided/);
    assert.notEqual(code, 0);
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
