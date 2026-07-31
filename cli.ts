#!/usr/bin/env node
import { readFileSync } from 'node:fs';
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

async function serverAlive(url: string): Promise<boolean> {
  try {
    const resp = await fetch(`${url}/health`, { signal: AbortSignal.timeout(2000) });
    return resp.ok;
  } catch {
    return false;
  }
}

function startServer(): Promise<string> {
  const serverPy = join(__dirname, '..', 'server.py');
  const python = platform() === 'win32' ? 'python' : 'python3';
  const proc = spawn(python, [serverPy], { stdio: ['ignore', 'pipe', 'ignore'] });

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Server start timed out')), 10_000);
    let url = '';
    proc.stdout!.on('data', (chunk: Buffer) => {
      url += chunk.toString();
      const line = url.split('\n')[0].trim();
      if (line.startsWith('http')) {
        clearTimeout(timer);
        proc.stdout!.destroy();
        proc.unref();
        resolve(line);
      }
    });
    proc.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
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
    '  generate    Generate Needle training data from tool definitions\n' +
    '  needletest  Evaluate an exported Needle model on a test set\n' +
    '  compare     Compare Needle vs Gemini Nano routing accuracy\n' +
    '\n' +
    'Options:\n' +
    '  --from LANG      Source language (translate, default: en)\n' +
    '  --to LANG        Target language (translate, required)\n' +
    '  --context CTX    Context for write command\n' +
    '  --tools PATH     Path to tool definitions JSON (generate)\n' +
    '  --output DIR     Output directory (generate, default: data/needle)\n' +
    '  --count N        Examples per tool (generate, default: 250)\n' +
    '  --model PATH     Path to exported .safetensors model (needletest)\n' +
    '  --checkpoint     Path to training .pkl checkpoint (needletest)\n' +
    '  --needle-model   Path to exported .safetensors model (compare)\n' +
    '  --test PATH      Path to test.jsonl (needletest/compare, default: data/needle/test.jsonl)\n' +
    '\n' +
    'Pipe text via stdin: cat file.txt | chrome-ai summarize\n',
  );
  process.exit(1);
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0];

  if (!cmd || !['prompt', 'summarize', 'translate', 'write', 'generate', 'needletest', 'compare'].includes(cmd)) {
    usage();
  }

  if (cmd === 'needletest') {
    const { flags, rest } = parseFlags(args.slice(1), ['model', 'checkpoint', 'test']);
    const testPath = flags['test'] || rest[0] || 'data/needle/test.jsonl';
    const python = platform() === 'win32' ? 'python' : 'python3';
    const evalArgs = [join(__dirname, '..', 'scripts', 'eval.py'), '--test', testPath];
    if (flags['model']) {
      evalArgs.push('--model', flags['model']);
    } else if (flags['checkpoint']) {
      evalArgs.push('--checkpoint', flags['checkpoint']);
    } else {
      process.stderr.write('needletest requires --model or --checkpoint\n');
      process.exit(1);
    }
    const proc = spawn(python, evalArgs, { stdio: 'inherit' });
    proc.on('exit', (code) => process.exit(code ?? 1));
    return;
  }

  if (cmd === 'compare') {
    const { flags, rest } = parseFlags(args.slice(1), ['needle-model', 'test']);
    if (!flags['needle-model']) {
      process.stderr.write('compare requires --needle-model <path>\n');
      process.exit(1);
    }
    const python = platform() === 'win32' ? 'python' : 'python3';
    const compareArgs = [
      join(__dirname, '..', 'scripts', 'compare.py'),
      '--needle-model', flags['needle-model'],
      '--test', flags['test'] || 'data/needle/test.jsonl',
    ];
    const proc = spawn(python, compareArgs, { stdio: 'inherit' });
    proc.on('exit', (code) => process.exit(code ?? 1));
    return;
  }

  if (cmd === 'generate') {
    const { flags, rest } = parseFlags(args.slice(1), ['tools', 'output', 'count', 'mode']);
    const toolsPath = flags['tools'] || rest[0];
    if (!toolsPath) {
      process.stderr.write('generate requires --tools <path> or <path> as argument\n');
      process.exit(1);
    }
    const raw = readFileSync(toolsPath, 'utf-8');
    const tools = JSON.parse(raw);
    const { generateTrainingData } = await import('./src/generate.js');
    await generateTrainingData(tools, {
      outputDir: flags['output'] || 'data/needle',
      positivesPerTool: flags['count'] ? parseInt(flags['count'], 10) : undefined,
    });
    process.exit(0);
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

  const { prompt, summarize, translate, write, DEFAULT_URL } = await import('./index.js');

  if (!process.env.CHROME_AI_URL) {
    if (await serverAlive(DEFAULT_URL)) {
      process.env.CHROME_AI_URL = DEFAULT_URL;
    } else {
      const url = await startServer();
      process.env.CHROME_AI_URL = url;
      process.stderr.write(`chrome-ai: started server — open ${url} in Chrome to process jobs\n`);
    }
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