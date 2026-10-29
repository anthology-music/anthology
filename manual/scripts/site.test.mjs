import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { problems } from './check-pages.mjs';
import { missingScreenshots, screenshotNames } from './check-screenshots.mjs';
import { expectedPages, partsOf } from './pages.mjs';
import { compareTags, publish, redirectPage, updateVersions } from './publish-site.mjs';

const config = `
  { dir: 'general', title: {}, pages: [ { path: '', title: {} }, { path: 'roles', title: {} }, ], },
`;

test('every page is expected in both languages', () => {
  const pages = expectedPages(partsOf(config));
  assert.deepEqual(pages, [
    'de/general/index.md',
    'de/general/roles.md',
    'de/index.md',
    'general/index.md',
    'general/roles.md',
    'index.md',
  ]);
  assert.deepEqual(
    problems(
      pages,
      pages.filter((page) => page !== 'de/general/roles.md'),
    ),
    ['missing: de/general/roles.md'],
  );
  assert.deepEqual(problems(pages, [...pages, 'de/extra.md']), ['not listed: de/extra.md']);
});

test('tags are ordered by version, release candidates first', () => {
  assert.ok(compareTags('v0.10.0', 'v0.9.0') > 0);
  assert.ok(compareTags('v1.0.0-rc.1', 'v1.0.0') < 0);
});

test('versions.json lists releases newest first', () => {
  let versions = updateVersions({}, 'next', null);
  versions = updateVersions(versions, 'v0.1', 'v0.1.0');
  versions = updateVersions(versions, 'v0.2', 'v0.2.0');
  versions = updateVersions(versions, 'v0.1', 'v0.1.1');
  assert.deepEqual(versions, {
    latest: 'v0.2',
    next: true,
    releases: [
      { path: 'v0.2', tag: 'v0.2.0' },
      { path: 'v0.1', tag: 'v0.1.1' },
    ],
  });
});

function build(label) {
  const folder = mkdtempSync(join(tmpdir(), 'manual-build-'));
  writeFileSync(join(folder, 'index.html'), label);
  return folder;
}

test('publishing places main under next/ and releases under vX.Y/, the root leads to the newest', () => {
  const site = mkdtempSync(join(tmpdir(), 'manual-site-'));
  const root = () => readFileSync(join(site, 'index.html'), 'utf8');
  publish(site, build('main'), 'next', null, '/anthology/');
  assert.match(root(), /url=\/anthology\/next\//);
  publish(site, build('0.1'), 'v0.1', 'v0.1.0', '/anthology/');
  publish(site, build('main again'), 'next', null, '/anthology/');
  assert.match(root(), /url=\/anthology\/v0\.1\//);
  assert.equal(readFileSync(join(site, '404.html'), 'utf8'), root());
  assert.equal(readFileSync(join(site, 'next/index.html'), 'utf8'), 'main again');
  publish(site, build('0.2'), 'v0.2', 'v0.2.0', '/anthology/');
  assert.match(root(), /url=\/anthology\/v0\.2\//);
  assert.equal(readFileSync(join(site, 'v0.1/index.html'), 'utf8'), '0.1');
  assert.equal(JSON.parse(readFileSync(join(site, 'versions.json'), 'utf8')).latest, 'v0.2');
});

test('the root redirect keeps deep links and stops inside a version', () => {
  const script = redirectPage('/anthology/', 'v0.2').match(/<script>\n([\s\S]*?)\n<\/script>/)[1];
  const run = (pathname) => {
    const result = { replaced: null, text: null };
    const location = {
      pathname,
      search: '',
      hash: '#x',
      replace: (url) => (result.replaced = url),
    };
    const document = {
      body: {
        set textContent(value) {
          result.text = value;
        },
      },
    };
    new Function('location', 'document', script)(location, document);
    return result;
  };
  assert.equal(
    run('/anthology/de/guide/listening').replaced,
    '/anthology/v0.2/de/guide/listening#x',
  );
  assert.equal(run('/anthology/').replaced, '/anthology/v0.2/#x');
  assert.equal(run('/anthology/v0.1/missing').text, 'Page not found.');
});

test('a publication build needs every screenshot in both languages', () => {
  assert.deepEqual(
    screenshotNames('<Screenshot name="player" alt="x" />\n<Screenshot alt="y" name="queue" />'),
    ['player', 'queue'],
  );
  const folder = mkdtempSync(join(tmpdir(), 'manual-pages-'));
  writeFileSync(join(folder, 'index.md'), '<Screenshot name="player" alt="The player" />');
  mkdirSync(join(folder, 'public/screenshots/en'), { recursive: true });
  writeFileSync(join(folder, 'public/screenshots/en/player.png'), '');
  assert.deepEqual(missingScreenshots(folder), ['public/screenshots/de/player.png']);
});
