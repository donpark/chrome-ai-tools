#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { platform } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString().trim();
}

function startServer(): Promise<string> {
  const serverPy = join(__dirname, '..', 'server.py');
  const python = platform() === 'win32' ? 'python' : 'python3';
  const proc = spawn(python, [serverPy], { stdio: ['ignore', 'pipe', 'inherit'] });

  return new Promise((resolve, reject) => {
    let url = '';
    proc.stdout!.on('data', (chunk: Buffer) => {
      url += chunk.toString();
      const line = url.split('\n')[0].trim();
      if (line.startsWith('http')) {
        proc.stdout!.removeAllListeners();
        proc.stdout!.destroy();
        resolve(line);
      }
    });
    proc.on('error', reject);
    setTimeout(() => reject(new Error('Server start timed out')), 10_000);
  });
}

function parseFlags(args: string[], flagNames: string[]): { flags: Record<string, string>; rest: string[] } {
  const result: Record<string, string> = {};
  const rest: string[] = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--') && flagNames.includes(args[i].slice(2))) {
      const name = args[i].slice(2);
      result[name] = args[i + 1] ?? '';
      i++;
    } else {
      rest.push(args[i]);
    }
  }
  return { flags: result, rest };
}

function usage(): never {
  process.stderr.write(
    'Usage: chrome-ai <command> [options] [text]\n' +
    '\n' +
    'Commands:\n' +
    '  prompt      Send a prompt to the language model\n' +
    '  summarize   Summarize text\n' +
    '  translate   Translate text (requires --from and --to)\n' +
    '  write       Generate or rewrite text\n' +
    '\n' +
    'Options:\n' +
    '  --from LANG   Source language (translate, default: en)\n' +
    '  --to LANG     Target language (translate, required)\n' +
    '  --context CTX Context for write command\n' +
    '\n' +
    'Pipe text via stdin: cat file.txt | chrome-ai summarize\n',
  );
  process.exit(1);
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0];

  if (!cmd || !['prompt', 'summarize', 'translate', 'write'].includes(cmd)) {
    usage();
  }

  const { flags, rest } = parseFlags(args.slice(1), ['from', 'to', 'context']);
  let text = rest.join(' ').trim();
  if (!text && !process.stdin.isTTY) {
    text = await readStdin();
  }
  if (!text) {
    process.stderr.write('No text provided.\n');
    process.exit(1);
  }

  // Build API call
  const { prompt, summarize, translate, write } = await import('./index.js');

  if (!process.env.CHROME_AI_URL) {
    const url = await startServer();
    process.env.CHROME_AI_URL = url;
  }

  let result: string;
  switch (cmd) {
    case 'prompt':
      result = await prompt({ user: text });
      break;
    case 'summarize':
      result = await summarize(text);
      break;
    case 'translate': {
      const from = flags['from'] || 'en';
      const to = flags['to'];
      if (!to) {
        process.stderr.write('translate requires --to LANG\n');
        process.exit(1);
      }
      result = await translate(text, from, to);
      break;
    }
    case 'write':
      result = await write(text, flags['context']);
      break;
    default:
      usage();
  }

  process.stdout.write(result + '\n');
}

main().catch((err) => {
  process.stderr.write(`chrome-ai: ${err.message}\n`);
  process.exit(1);
});
