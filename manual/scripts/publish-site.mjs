// Places a build of the manual into a checkout of the branch gh-pages (CI only, pages.yml):
//   MANUAL_SITE_ROOT=/anthology/ node scripts/publish-site.mjs <site> <build> <target> [--tag vX.Y.Z]
// <target> is "next" (main) or "vX.Y" (a release). The site root leads to the newest release, or to
// next/ while there is none: a build only works below the base it was built for, so the root holds
// redirects (index.html, and 404.html for deep links) instead of a copy. versions.json lists the
// releases.
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export function compareTags(a, b) {
  const parse = (tag) =>
    tag
      .replace(/^v/, '')
      .split(/[.-]/)
      .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
  const [x, y] = [parse(a), parse(b)];
  for (let index = 0; index < 3; index += 1) if (x[index] !== y[index]) return x[index] - y[index];
  // A version with a suffix (rc) comes before the same version without one.
  return (x.length > 3 ? -1 : 0) - (y.length > 3 ? -1 : 0);
}

export function updateVersions(versions, target, tag) {
  const next = { latest: null, releases: [], next: false, ...versions };
  if (target === 'next') return { ...next, next: true };
  const releases = next.releases.filter((release) => release.path !== target);
  releases.push({ path: target, tag });
  releases.sort((a, b) => compareTags(b.tag, a.tag));
  return { ...next, releases, latest: releases[0].path };
}

function copyInto(build, folder) {
  rmSync(folder, { recursive: true, force: true });
  mkdirSync(folder, { recursive: true });
  cpSync(build, folder, { recursive: true });
}

/** The root pages that lead to <target>/, keeping the path of a deep link. */
export function redirectPage(siteRoot, target) {
  const script = `const root = ${JSON.stringify(siteRoot)};
const target = ${JSON.stringify(`${target}/`)};
const rest = location.pathname.startsWith(root) ? location.pathname.slice(root.length) : '';
if (/^(next|v\\d+\\.\\d+)(\\/|$)/.test(rest)) document.body.textContent = 'Page not found.';
else location.replace(root + target + rest + location.search + location.hash);`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Anthology manual</title>
<meta name="robots" content="noindex">
<noscript><meta http-equiv="refresh" content="0; url=${siteRoot}${target}/"></noscript>
</head>
<body>
<p><a href="${siteRoot}${target}/">Anthology manual</a></p>
<script>
${script}
</script>
</body>
</html>
`;
}

export function publish(site, build, target, tag, siteRoot = '/') {
  if (target !== 'next' && !/^v\d+\.\d+$/.test(target)) throw new Error(`bad target ${target}`);
  const file = join(site, 'versions.json');
  const before = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : {};
  const versions = updateVersions(before, target, tag);
  copyInto(build, join(site, target));
  const page = redirectPage(siteRoot, versions.latest ?? 'next');
  writeFileSync(join(site, 'index.html'), page);
  writeFileSync(join(site, '404.html'), page);
  writeFileSync(file, `${JSON.stringify(versions, null, 2)}\n`);
  writeFileSync(join(site, '.nojekyll'), '');
  return versions;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [site, build, target, flag, tag] = process.argv.slice(2);
  if (!site || !build || !target || (target !== 'next' && (flag !== '--tag' || !tag))) {
    console.error('usage: publish-site.mjs <site> <build> <next|vX.Y> [--tag vX.Y.Z]');
    process.exit(2);
  }
  const siteRoot = process.env.MANUAL_SITE_ROOT ?? '/';
  console.log(JSON.stringify(publish(site, build, target, tag ?? null, siteRoot)));
}
