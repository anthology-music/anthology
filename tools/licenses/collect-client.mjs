// The license files of the client's production dependencies (change first-release): run in the
// image's web stage, where the client is installed, and copied to /app/licenses/client.
// Usage: node tools/licenses/collect-client.mjs <target folder>
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const target = process.argv[2];
if (!target) throw new Error('usage: collect-client.mjs <target folder>');
const LICENSE_FILES = /^(licen[cs]e|copying|notice|authors)/i;
const output = execFileSync('pnpm', ['--filter', 'client', 'licenses', 'list', '--prod', '--json'], {
  encoding: 'utf8',
});
mkdirSync(target, { recursive: true });
let copied = 0;
for (const entries of Object.values(JSON.parse(output))) {
  for (const entry of entries) {
    entry.versions.forEach((version, index) => {
      const path = entry.paths[index];
      if (!path || !existsSync(path) || !statSync(path).isDirectory()) return;
      const folder = join(target, `${entry.name.replace('/', '__')}-${version}`);
      for (const name of readdirSync(path)) {
        if (!LICENSE_FILES.test(name)) continue;
        mkdirSync(folder, { recursive: true });
        copyFileSync(join(path, name), join(folder, name));
        copied += 1;
      }
    });
  }
}
console.log(`${copied} license files of the client's dependencies in ${target}`);
