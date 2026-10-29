/**
 * Screenshots of the manual (ADR 0023): a walkthrough against the end-to-end server, once to
 * prepare the data (setup, imports, an order, a cover, a playlist, plays), then once per interface
 * language. Each screenshot has a stable name: manual/public/screenshots/<language>/<name>.png,
 * shown by <Screenshot name="…" />. Only generated data appears (library generator, tones,
 * generated cover).
 */
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { type Browser, expect, type Page, test } from '@playwright/test';

const ADMIN = { name: 'Lukas', username: 'lukas', password: 'correct horse battery' };
const OUT = fileURLToPath(new URL('../public/screenshots/', import.meta.url));
const FAKE_RAUMFELD = `http://127.0.0.1:${process.env.ANTHOLOGY_E2E_FAKE_RAUMFELD_PORT ?? 8431}`;
const LANGUAGES = ['en', 'de'] as const;
type Language = (typeof LANGUAGES)[number];

test.describe.configure({ mode: 'serial' });

let release = '';

async function shoot(page: Page, language: Language, name: string): Promise<void> {
  mkdirSync(`${OUT}${language}`, { recursive: true });
  // Let lazy images and animations settle.
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}${language}/${name}.png` });
}

async function signIn(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[autocomplete="username"]').fill(ADMIN.username);
  await page.locator('input[type="password"]').fill(ADMIN.password);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/local\/albums$/);
}

async function inLanguage(browser: Browser, language: Language): Promise<Page> {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    colorScheme: 'dark',
    locale: language === 'de' ? 'de-CH' : 'en-GB',
  });
  await context.addInitScript((value) => {
    globalThis.localStorage.setItem('anthology.language', value);
  }, language);
  return context.newPage();
}

/** A generated cover: a gradient with circles, drawn in the browser. */
async function generatedCover(page: Page): Promise<Buffer> {
  const data = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 600;
    const context = canvas.getContext('2d')!;
    const gradient = context.createLinearGradient(0, 0, 600, 600);
    gradient.addColorStop(0, '#1d3557');
    gradient.addColorStop(1, '#e76f51');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 600, 600);
    for (let index = 0; index < 6; index += 1) {
      context.beginPath();
      context.arc(300, 300, 40 + index * 45, 0, Math.PI * 2);
      context.strokeStyle = `rgba(255, 255, 255, ${0.5 - index * 0.07})`;
      context.lineWidth = 8;
      context.stroke();
    }
    return canvas.toDataURL('image/png').split(',')[1]!;
  });
  return Buffer.from(data, 'base64');
}

test('prepare: setup, imports, an order, a cover, a playlist and plays', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/setup$/);
  await page.getByLabel('Anzeigename').fill(ADMIN.name);
  await page.getByLabel('Benutzername').fill(ADMIN.username);
  await page.getByLabel('Passwort').fill(ADMIN.password);
  await page.getByRole('button', { name: 'Konto anlegen' }).click();
  await expect(page).toHaveURL(/\/local\/albums$/);

  // Two folder imports: the album, and a remaster that the review list asks about.
  for (const folder of ['Kassette 1985', 'Remaster 1999']) {
    await page.goto('/streaming');
    await page.getByTestId('import-folder').click();
    const dialog = page.getByTestId('import-dialog');
    await dialog.getByRole('button', { name: 'imports öffnen' }).click();
    await dialog.getByRole('button', { name: `${folder} öffnen` }).click();
    await dialog.getByTestId('import-scan').click();
    await page.getByTestId('import-confirm').click({ timeout: 30_000 });
    await expect(page.getByTestId('import-status').first()).toContainText('Fertig', {
      timeout: 30_000,
    });
  }

  // An order from the fake source service.
  await page.getByTestId('source-query').fill('https://fake.example/album/2');
  await page.getByTestId('source-submit').click();
  await expect(page.getByTestId('resolved')).toContainText('Bergwind');
  await page.getByTestId('source-order').click();
  await expect(
    page.locator('[data-testid^="order-"]').filter({ hasText: 'Bergwind' }).first(),
  ).toContainText('Fertig', { timeout: 90_000 });

  // A cover, a favorite, a shared playlist with the album, and plays for the history.
  await page.goto('/local/albums');
  const kassette = page.locator('[data-testid^="release-"]').filter({ hasText: 'Kassette 1985' });
  release = (await kassette.first().getAttribute('data-testid'))!.replace('release-', '');
  await kassette.first().click();
  await page.getByTestId('cover-upload').setInputFiles({
    name: 'cover.png',
    mimeType: 'image/png',
    buffer: await generatedCover(page),
  });
  await expect(page.getByTestId('album-cover').locator('img')).toBeVisible();
  await page.getByTestId(`favorite-release-${release}`).click();
  await page.getByTestId('release-to-playlist').click();
  await page.getByTestId('add-to-new-name').fill('Sommerabend');
  await page.getByTestId('add-to-new').click();
  await expect(page.getByTestId('playlist-message')).toContainText('Sommerabend');
  await page.getByTestId('play-release').click();
  await expect(page.getByTestId('player-title')).toHaveText('Frühling');
  // The first track (8 s) counts after half of it.
  await page.waitForTimeout(6_000);
  await page.getByTestId('player-next').click();
  await page.waitForTimeout(5_000);
  await page.getByTestId('player-toggle').click();
});

for (const language of LANGUAGES) {
  test(`screenshots (${language})`, async ({ browser }) => {
    const page = await inLanguage(browser, language);

    await page.goto('/login');
    await shoot(page, language, 'sign-in');
    await signIn(page);

    // Library
    await expect(page.locator('[data-testid^="release-"]').first()).toBeVisible();
    await shoot(page, language, 'library-albums');
    await page.goto('/local/artists');
    await expect(page.locator('[role="listitem"]').first()).toBeVisible();
    await shoot(page, language, 'library-artists');
    await page.goto(`/local/releases/${release}`);
    await expect(page.getByTestId('album-cover').locator('img')).toBeVisible();
    await shoot(page, language, 'release');
    await page.goto(`/local/search?q=${encodeURIComponent('Frühling')}`);
    await page.waitForTimeout(1_000);
    await shoot(page, language, 'search');

    // Listening
    await page.goto(`/local/releases/${release}`);
    await page.getByTestId('play-release').click();
    await expect(page.getByTestId('player-title')).toBeVisible();
    await page.getByTestId('player-toggle').click();
    await shoot(page, language, 'player');
    await page.getByTestId('player-queue').click();
    await shoot(page, language, 'queue');
    await page.getByTestId('player-queue').click();

    // Speakers
    await page.getByTestId('output-picker').click();
    await expect(page.getByTestId('output-zone-Wohnzimmer')).toBeVisible();
    await shoot(page, language, 'output-picker');
    await page.getByTestId('output-manage').click();
    await expect(page.getByTestId('zone-manager')).toBeVisible();
    await shoot(page, language, 'zone-manager');
    await page.keyboard.press('Escape');

    // Covers and editing
    await page.getByTestId('open-gallery').click();
    await expect(page.getByTestId('gallery')).toBeVisible();
    await shoot(page, language, 'gallery');
    await page.keyboard.press('Escape');
    await page.getByTestId('mode-edit').click();
    await page.getByTestId('edit-release').click();
    await page.waitForTimeout(500);
    await shoot(page, language, 'tag-editor');
    await page.keyboard.press('Escape');
    await page.getByTestId('mode-listen').click();

    // Playlists, favorites, history
    await page.goto('/local/playlists');
    await expect(page.getByTestId('playlist-Sommerabend')).toBeVisible();
    await shoot(page, language, 'playlists');
    await page.getByTestId('playlist-Sommerabend').click();
    await expect(page.locator('[data-testid^="entry-"][draggable="true"]').first()).toBeVisible();
    await shoot(page, language, 'playlist');
    await page.goto('/local/favorites');
    await shoot(page, language, 'favorites');
    await page.goto('/local/history');
    await shoot(page, language, 'history');

    // Review and conflicts
    await page.goto('/review');
    await page.waitForTimeout(1_000);
    await shoot(page, language, 'review');
    await page.goto('/conflicts');
    await page.waitForTimeout(1_000);
    await shoot(page, language, 'conflicts');

    // Acquiring
    await page.goto('/streaming');
    await expect(page.getByTestId('source-none')).toHaveCount(0, { timeout: 30_000 });
    await page.getByTestId('source-query').fill('https://fake.example/album/1');
    await page.getByTestId('source-submit').click();
    await expect(page.getByTestId('resolved')).toBeVisible();
    await shoot(page, language, 'source-search');
    await page.getByTestId('import-folder').click();
    await expect(page.getByTestId('import-dialog')).toBeVisible();
    await shoot(page, language, 'import-dialog');
    await page.keyboard.press('Escape');

    // Settings
    await page.goto('/settings');
    await shoot(page, language, 'settings');
    await page.getByTestId('about-licenses').scrollIntoViewIfNeeded();
    await shoot(page, language, 'about');

    await page.context().close();
  });
}

test('the fake Raumfeld host is up', async ({ request }) => {
  expect((await request.get(`${FAKE_RAUMFELD}/test/state`)).ok()).toBe(true);
});
