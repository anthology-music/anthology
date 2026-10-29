// The pages the manual must have: every page of the parts (.vitepress/config.mts) in English
// (root) and German (de/), plus the two home pages.
import { readFileSync } from 'node:fs';

/** The part list, read from the config's source (no TypeScript loader needed). */
export function partsOf(configSource) {
  const parts = [];
  const partPattern = /dir: '([^']+)',[\s\S]*?pages: \[([\s\S]*?)\],\s*\},/g;
  for (const match of configSource.matchAll(partPattern)) {
    const paths = [...match[2].matchAll(/path: '([^']*)'/g)].map((page) => page[1]);
    parts.push({ dir: match[1], paths });
  }
  return parts;
}

export function expectedPages(parts) {
  const files = ['index.md', 'de/index.md'];
  for (const part of parts) {
    for (const path of part.paths) {
      const file = `${part.dir}/${path || 'index'}.md`;
      files.push(file, `de/${file}`);
    }
  }
  return files.sort();
}

export function readParts(root) {
  return partsOf(readFileSync(new URL('.vitepress/config.mts', root), 'utf8'));
}
