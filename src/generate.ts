/**
 * Needle training data generator.
 *
 * Produces Needle-format JSONL from user-provided tool definitions.
 * Two modes: LLM (Gemini) and schematic (no API key needed).
 *
 * Needle JSONL format per line:
 *   {"query":"...","tools":"[stringified ToolDefinition[]]","answers":"[{\"name\":\"...\",\"arguments\":{...}}]"}
 *
 * Usage:
 *   chrome-ai generate --tools tools.json --output data/needle/
 *
 *   # or as a TS API:
 *   import { generateTrainingData } from 'chrome-ai-tools';
 *   await generateTrainingData(tools, { outputDir: 'data/needle' });
 */

import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ToolDefinition, ToolRoute } from './needle-types.js';

// ── Public API ──

export interface GenerateOptions {
  /** Positive examples per tool (default: 250) */
  positivesPerTool?: number;
  /** Null/unsupported query examples (default: 350) */
  nulls?: number;
  /** Contrastive/ambiguous examples (default: 200) */
  contrastive?: number;
  /** Validation split percentage (default: 0.10) */
  valPct?: number;
  /** Test split percentage (default: 0.10) */
  testPct?: number;
  /** LLM generator for diverse phrasings. Uses schematic fallback if omitted. */
  llm?: (query: string, tools: ToolDefinition[]) => Promise<string[]>;
  /** Output directory (default: 'data/needle') */
  outputDir?: string;
}

export interface Example {
  query: string;
  tools: string;       // JSON string of ToolDefinition[]
  answers: string;     // JSON string of [{name, arguments}]
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

/**
 * Generate Needle training data from tool definitions.
 * Writes train.jsonl, val.jsonl, test.jsonl to outputDir.
 */
export async function generateTrainingData(
  tools: ToolDefinition[],
  opts: GenerateOptions = {},
): Promise<void> {
  const {
    positivesPerTool = 250,
    nulls = 350,
    contrastive = 200,
    valPct = 0.10,
    testPct = 0.10,
    llm,
    outputDir = 'data/needle',
  } = opts;

  const generator = llm || schematicGenerator;
  const examples = await generateAll(tools, { positivesPerTool, nulls, contrastive, generator });
  splitAndWrite(examples, { valPct, testPct, outputDir });
}

// ── Generation ──

interface GenOpts {
  positivesPerTool: number;
  nulls: number;
  contrastive: number;
  generator: (query: string, tools: ToolDefinition[]) => Promise<string[]>;
}

async function generateAll(tools: ToolDefinition[], opts: GenOpts): Promise<Example[]> {
  const { positivesPerTool, nulls, contrastive, generator } = opts;
  const examples: Example[] = [];

  // 1. Positive examples per tool
  for (const tool of tools) {
    const phrasings = await generator(tool.name + ': ' + tool.description, tools);
    for (let i = 0; i < positivesPerTool; i++) {
      const query = pick(phrasings);
      const contextTools = shuffleTools(tools);
      examples.push(makeExample(query, tool.name, contextTools));
    }
  }

  // 2. Null / unsupported examples
  const nullPhrasings = await generator('Generate unsupported or off-topic user queries that do not match any tool.', tools);
  for (let i = 0; i < nulls; i++) {
    const query = pick(nullPhrasings);
    examples.push(makeExample(query, null, shuffleTools(tools)));
  }

  // 3. Contrastive examples (ambiguous between tools)
  const contrastivePairs = generateContrastivePairs(tools);
  for (const [q, target] of contrastivePairs) {
    examples.push(makeExample(q, target, shuffleTools(tools)));
  }

  return shuffle(examples);
}

function makeExample(query: string, toolName: string | null, tools: ToolDefinition[]): Example {
  const answers: ToolCall[] = toolName
    ? [{ name: toolName, arguments: {} }]
    : [];
  return {
    query,
    tools: JSON.stringify(tools),
    answers: JSON.stringify(answers),
  };
}

// ── Schematic fallback generator ──

async function schematicGenerator(_prompt: string, tools: ToolDefinition[]): Promise<string[]> {
  // Generate phrases directly from tool names/descriptions without an LLM
  const names = tools.map(t => t.name);
  const descs = tools.map(t => t.description);
  const results: string[] = [];

  // For each tool, generate both direct and rephrased variants
  for (let i = 0; i < tools.length; i++) {
    const t = tools[i];
    const nameParts = t.name.split('_');
    const verb = nameParts[0] || 'use';
    const noun = nameParts.slice(1).join(' ') || t.name;

    results.push(t.description);
    results.push(`${verb} ${noun}`);
    results.push(`I want to ${verb} ${noun}`);
    results.push(`Can you ${verb} ${noun}?`);
    results.push(`Please ${verb} ${noun} for me`);
    results.push(`${verb} the ${noun} content`);
    results.push(`Help me ${verb} ${noun}`);
  }

  // Null/unsupported phrases
  const nulls = [
    'What is the weather?', 'Tell me a joke', 'What time is it?',
    'Play some music', 'Send an email', 'Set an alarm',
    'What is 2+2?', 'Bookmark this page', 'Print this document',
    'Order pizza', 'Translate this page', 'Turn on dark mode',
    'What is the capital of France?', 'Schedule a meeting',
    'Remind me to call John', 'Search for cheap flights',
  ];
  results.push(...nulls);

  return results;
}

// ── Contrastive pair generator ──

function generateContrastivePairs(tools: ToolDefinition[]): [string, string][] {
  const pairs: [string, string][] = [];
  // Generate pairs between every pair of tools
  for (let i = 0; i < tools.length; i++) {
    for (let j = i + 1; j < tools.length; j++) {
      const a = tools[i], b = tools[j];
      // Ambiguous: query referencing both tools
      pairs.push([`${a.description} and also ${b.description}`, a.name]);
      pairs.push([`Can you ${b.description}?`, b.name]);
      // Near-duplicate: one tool's description with the other's name
      pairs.push([`${b.description}`, b.name]);
      pairs.push([`I need to ${a.name.split('_').join(' ')}`, a.name]);
    }
  }
  return pairs;
}

// ── Split and write ──

function splitAndWrite(
  examples: Example[],
  opts: { valPct: number; testPct: number; outputDir: string },
): void {
  const { valPct, testPct, outputDir } = opts;

  const deduped = dedupe(examples);
  const byQuery = new Map<string, Example[]>();
  for (const ex of deduped) {
    const q = ex.query;
    if (!byQuery.has(q)) byQuery.set(q, []);
    byQuery.get(q)!.push(ex);
  }

  const train: Example[] = [];
  const val: Example[] = [];
  const test: Example[] = [];

  for (const [, group] of byQuery) {
    const h = hashStr(group[0].query) % 100;
    if (h < valPct * 100) {
      val.push(...group);
    } else if (h < (valPct + testPct) * 100) {
      test.push(...group);
    } else {
      train.push(...group);
    }
  }

  mkdirSync(resolve(outputDir), { recursive: true });

  writeLines(resolve(outputDir, 'train.jsonl'), train);
  writeLines(resolve(outputDir, 'val.jsonl'), val);
  writeLines(resolve(outputDir, 'test.jsonl'), test);

  const total = train.length + val.length + test.length;
  console.log(`\n  Generated ${total} Needle-format examples:`);
  console.log(`    train.jsonl: ${train.length}`);
  console.log(`    val.jsonl:   ${val.length}`);
  console.log(`    test.jsonl:  ${test.length}`);
  console.log(`    Data dir:    ${resolve(outputDir)}\n`);

  const allExs = [...train, ...val, ...test];
  const tools = [...new Set(allExs.map(e => {
    const a: ToolCall[] = JSON.parse(e.answers);
    return a.length > 0 ? a[0].name : 'null';
  }))].sort();
  console.log(`  Tool distribution:`);
  for (const t of tools) {
    const count = allExs.filter(e => {
      const a: ToolCall[] = JSON.parse(e.answers);
      return a.length > 0 ? a[0].name === t : t === 'null';
    }).length;
    console.log(`    ${t.padEnd(28)} ${count}/${total} (${(count / total * 100).toFixed(1)}%)`);
  }
  console.log();
}

// ── Helpers ──

function pick<T>(arr: T[]): T { return arr[Math.floor(Math.random() * arr.length)]; }

function shuffle<T>(arr: T[]): T[] {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function shuffleTools(tools: ToolDefinition[]): ToolDefinition[] {
  return shuffle([...tools]);
}

function dedupe(examples: Example[]): Example[] {
  const seen = new Set<string>();
  return examples.filter(e => {
    const key = `${e.query}|${e.tools}|${e.answers}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h) + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

function writeLines(path: string, data: Example[]): void {
  const lines = data.map(e => JSON.stringify(e)).join('\n');
  writeFileSync(path, lines + '\n');
}
