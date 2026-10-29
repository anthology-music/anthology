// A publication build needs every screenshot the pages show, in both languages (ADR 0023):
// <Screenshot name="x" /> in a page needs public/screenshots/<language>/x.png from the walkthrough.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { markdownFiles } from './check-pages.mjs';

export function screenshotNames(markdown) {
  return [...markdown.matchAll(/<Screenshot\s[^>]*name="([^"]+)"/g)].map((match) => match[1]);
}

export function missingScreenshots(directory) {
  const names = new Set();
  for (const file of markdownFiles(directory)) {
    for (const name of screenshotNames(readFileSync(join(directory, file), 'utf8')))
      names.add(name);
  }
  const missing = [];
  for (const name of [...names].sort()) {
    for (const language of ['en', 'de']) {
      const file = `public/screenshots/${language}/${name}.png`;
      if (!existsSync(join(directory, file))) missing.push(file);
    }
  }
  return missing;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const missing = missingScreenshots(fileURLToPath(new URL('../', import.meta.url)));
  for (const file of missing) console.error(`missing screenshot: ${file}`);
  if (missing.length) process.exit(1);
  console.log('every screenshot exists in English and German');
}
