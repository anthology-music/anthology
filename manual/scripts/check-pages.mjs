// Every page exists in English and German, and no page is outside the part list (ADR 0023).
import { readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expectedPages, readParts } from './pages.mjs';

const root = new URL('../', import.meta.url);
const directory = fileURLToPath(root);
const skipped = new Set(['node_modules', '.vitepress', 'public', 'walkthrough', 'scripts']);

export function markdownFiles(folder, base = folder) {
  const found = [];
  for (const name of readdirSync(folder)) {
    if (skipped.has(name)) continue;
    const path = join(folder, name);
    if (statSync(path).isDirectory()) found.push(...markdownFiles(path, base));
    else if (name.endsWith('.md') && name !== 'README.md') found.push(relative(base, path));
  }
  return found.sort();
}

export function problems(expected, present) {
  const missing = expected.filter((file) => !present.includes(file)).map((f) => `missing: ${f}`);
  const extra = present.filter((file) => !expected.includes(file)).map((f) => `not listed: ${f}`);
  return [...missing, ...extra];
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const found = problems(expectedPages(readParts(root)), markdownFiles(directory));
  for (const line of found) console.error(line);
  if (found.length) process.exit(1);
  console.log('every page exists in English and German');
}
