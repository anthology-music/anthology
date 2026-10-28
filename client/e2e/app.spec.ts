import { expect, test, type Page } from '@playwright/test';

const ADMIN = { name: 'Lukas', username: 'lukas', password: 'correct horse battery' };
const BUDGET_MS = 2_000;
const DEMO_ROWS = Number(process.env.ANTHOLOGY_E2E_DEMO_ROWS ?? 500_000);
const LIBRARY_TRACKS = Number(process.env.ANTHOLOGY_E2E_LIBRARY_TRACKS ?? 20_000);

test.describe.configure({ mode: 'serial' });

async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Benutzername').fill(ADMIN.username);
  await page.getByLabel('Passwort').fill(ADMIN.password);
  await page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(page).toHaveURL(/\/local\/albums$/);
}

test('a fresh installation starts with the setup and creates the admin', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/setup$/);

  await page.getByLabel('Anzeigename').fill(ADMIN.name);
  await page.getByLabel('Benutzername').fill(ADMIN.username);
  await page.getByLabel('Passwort').fill(ADMIN.password);
  await page.getByRole('button', { name: 'Konto anlegen' }).click();

  await expect(page).toHaveURL(/\/local\/albums$/);
  await expect(page.getByRole('status')).toHaveText('Verbunden · live');
});

test('signing out and in again', async ({ page }) => {
  await signIn(page);

  await page.getByRole('button', { name: 'Konto-Menü' }).click();
  await page.getByRole('menuitem', { name: 'Abmelden' }).or(page.getByText('Abmelden')).click();
  await expect(page).toHaveURL(/\/login$/);

  await signIn(page);
});

test('my devices shows this browser as the current device', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'Einstellungen' }).click();

  const devices = page.locator('#my-devices-title ~ ul li');
  await expect(devices.filter({ hasText: 'Dieses Gerät' })).toHaveCount(1);
});

test('the demo list meets the interaction budget, also for a jump', async ({ page }) => {
  await signIn(page);

  // Measured from the click in the loaded app, not including the dev server's first load.
  const started = Date.now();
  await page.getByRole('link', { name: 'Demo-Liste' }).click();
  await expect(page.getByTestId('demo-total')).toHaveText(
    // The app formats with the UI language (German).
    new Intl.NumberFormat('de').format(DEMO_ROWS),
  );
  await expect(page.locator('[role="listitem"][aria-posinset="1"] .item-list__main')).toBeVisible();
  const firstRows = Date.now() - started;

  const list = page.getByRole('list', { name: 'Demo-Liste' });
  const jumpStarted = Date.now();
  await list.evaluate((element, rows) => {
    const full = rows * 52;
    const ratio = (full - element.clientHeight) / (element.scrollHeight - element.clientHeight);
    element.scrollTop = (250_000 * 52) / Math.max(1, ratio);
  }, DEMO_ROWS);
  const target = page.locator('[role="listitem"][aria-posinset="250001"] .item-list__main');
  await expect(target).toBeVisible();
  const jump = Date.now() - jumpStarted;

  console.log(`first rows ${firstRows} ms, jump ${jump} ms`);
  expect(firstRows).toBeLessThanOrEqual(BUDGET_MS);
  expect(jump).toBeLessThanOrEqual(BUDGET_MS);
});

test('a demo job shows live progress and can be paused and resumed', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'Streaming' }).click();

  await page.getByTestId('start-demo-job').click();
  const job = page.locator('.job-row').first();
  const count = job.getByTestId('job-count');
  const status = job.locator('.job-status__text');
  await expect(count).toHaveText('0 / 12');

  // Each demo item takes one second; finished items must show up within one more second.
  await expect(count).toHaveText('1 / 12', { timeout: 3_000 });
  await expect(count).toHaveText('2 / 12', { timeout: 2_000 });
  await expect(status).toHaveText('Läuft');
  await expect(page.getByTestId('job-counter-running')).toHaveText('1');

  await job.getByTestId('job-pause').click();
  await expect(status).toHaveText('Pausiert');
  const pausedAt = await count.textContent();
  await page.waitForTimeout(1_500);
  await expect(count).toHaveText(pausedAt!);

  await job.getByTestId('job-resume').click();
  await expect(status).toHaveText('Läuft');
  await expect(count).not.toHaveText(pausedAt!, { timeout: 3_000 });

  await job.getByTestId('job-cancel').click();
  await expect(status).toHaveText('Abgebrochen');
  await expect(page.getByTestId('job-counter-total')).toHaveText('1');
});

test('browsing the library from an artist to an album, with reload and scroll restore', async ({
  page,
}) => {
  await signIn(page);
  const count = (section: string) =>
    page.getByTestId(`library-nav-${section}`).locator('.library-nav__count');
  await expect(count('tracks')).toHaveText(new Intl.NumberFormat('de').format(LIBRARY_TRACKS));
  await expect(count('releases')).toHaveText(/^[\d.]+$/);

  // Artist → album; the generated names are not fixed, so follow the links on the page.
  await page.getByTestId('library-nav-artists').click();
  await expect(page).toHaveURL(/\/local\/artists$/);
  const firstArtist = page.locator('[role="listitem"][aria-posinset="1"] [data-testid^="artist-"]');
  const artistName = (await firstArtist.locator('.library-row__title').textContent())!.trim();
  await firstArtist.click();
  await expect(page.getByTestId('artist-name')).toHaveText(artistName);

  await page.locator('[role="listitem"][aria-posinset="1"] [data-testid^="release-"]').click();
  await expect(page).toHaveURL(/\/local\/releases\/[0-9a-f-]+$/);
  const title = page.getByTestId('release-title');
  await expect(title).not.toHaveText('…');
  const albumTitle = await title.textContent();
  await expect(page.locator('[data-testid^="track-"]').first()).toBeVisible();
  await expect(page.locator('.breadcrumb')).toContainText(artistName);

  await page.reload();
  await expect(title).toHaveText(albumTitle!);
  await expect(page.locator('[data-testid^="track-"]').first()).toBeVisible();

  // Scroll the album section to position 1,000, open an album there and come back.
  await page.getByTestId('library-nav-releases').click();
  await expect(page).toHaveURL(/\/local\/albums$/);
  const list = page.getByRole('list', { name: 'Alben' });
  await expect(page.locator('[role="listitem"][aria-posinset="1"] a')).toBeVisible();
  await list.evaluate((element) => {
    const rows = Number(element.querySelector('[role="listitem"]')!.getAttribute('aria-setsize'));
    const full = rows * 52;
    const ratio = Math.max(
      1,
      (full - element.clientHeight) / (element.scrollHeight - element.clientHeight),
    );
    element.scrollTop = (1_000 * 52) / ratio;
  });
  const far = page.locator('[role="listitem"][aria-posinset="1001"] a');
  await expect(far).toBeVisible();
  await far.click();
  await expect(page).toHaveURL(/\/local\/releases\//);
  await page.goBack();
  await expect(page.locator('[role="listitem"][aria-posinset="1001"] a')).toBeVisible();
});

test('importing a server folder and browsing the new album', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'Streaming' }).click();

  await page.getByTestId('import-folder').click();
  const dialog = page.getByTestId('import-dialog');
  await dialog.getByRole('button', { name: 'imports öffnen' }).click();
  await dialog.getByRole('button', { name: 'Kassette 1985 öffnen' }).click();
  // The proposed mode is preselected (the test folders share one file system: a link).
  await expect(dialog.locator('input[name="import-mode"]:checked')).toHaveCount(1);
  await dialog.getByTestId('import-scan').click();

  // Nothing changes before the report is confirmed.
  const confirm = page.getByTestId('import-confirm');
  await expect(confirm).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('import-category-new')).toContainText('2 Dateien');
  await confirm.click();
  await expect(page.getByTestId('import-status').first()).toContainText('Fertig', {
    timeout: 30_000,
  });
  await expect(page.getByTestId('import-result')).toContainText('Importiert: 2');

  // "4 Jahreszeiten" sorts before the generated (alphabetic) names.
  await page.getByRole('link', { name: 'Lokal' }).click();
  await expect(page).toHaveURL(/\/local\/albums$/);
  const first = page.locator('[role="listitem"][aria-posinset="1"] [data-testid^="release-"]');
  await expect(first).toContainText('Kassette 1985');
  await first.click();
  await expect(page.getByTestId('release-title')).toHaveText('Kassette 1985');
  const tracks = page.locator('[data-testid^="track-"]');
  await expect(tracks).toHaveCount(2);
  await expect(tracks.first()).toContainText('Frühling');
  await expect(tracks.nth(1)).toContainText('Sommer');
});

test('a name match in the review list is merged on acceptance', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'Streaming' }).click();

  // "Frühling" again, with other audio: imported as its own recording plus a suggestion.
  await page.getByTestId('import-folder').click();
  const dialog = page.getByTestId('import-dialog');
  await dialog.getByRole('button', { name: 'imports öffnen' }).click();
  await dialog.getByRole('button', { name: 'Remaster 1999 öffnen' }).click();
  await dialog.getByTestId('import-scan').click();
  const confirm = page.getByTestId('import-confirm');
  await expect(confirm).toBeVisible({ timeout: 30_000 });
  await confirm.click();
  await expect(page.getByTestId('import-status').first()).toContainText('Fertig', {
    timeout: 30_000,
  });

  await page.getByRole('link', { name: /Prüfliste/ }).click();
  await expect(page).toHaveURL(/\/review$/);
  const row = page.locator('[data-testid^="review-row-"]').filter({ hasText: 'Frühling' });
  await expect(row).toHaveCount(1);
  await row.getByRole('button').click();
  await expect(page.getByTestId('review-detail')).toContainText('Gleiche Aufnahme?');
  await page.getByTestId('review-accept').click();
  await expect(page.getByTestId('review-message')).toContainText('Angenommen');
  await expect(page.getByTestId('review-empty')).toBeVisible();

  // The decision is recorded with the editor's name.
  await page.getByTestId('review-filter-status').selectOption('accepted');
  await page.locator('[data-testid^="review-row-"]').first().getByRole('button').click();
  await expect(page.getByTestId('review-decided')).toContainText(ADMIN.name);

  // Both albums keep their track: one recording, two contexts.
  await page.getByRole('link', { name: 'Lokal' }).click();
  await page.locator('[data-testid^="release-"]').filter({ hasText: 'Remaster 1999' }).click();
  await expect(page.locator('[data-testid^="track-"]')).toContainText(['Frühling']);
});

test('editing an album and undoing the edit from the history', async ({ page }) => {
  await signIn(page);
  const kassette = page
    .locator('[data-testid^="release-"]')
    .filter({ hasText: 'Kassette 1985' })
    .first();
  await kassette.click();
  await expect(page.getByTestId('release-title')).toHaveText('Kassette 1985');

  // All tracks of the album at once (sent as the list's rule), then the album itself.
  await page.getByTestId('mode-edit').click();
  await page.getByTestId('select-all').click();
  await expect(page.getByTestId('edit-count')).toContainText('2 ausgewählt');
  await page.getByTestId('edit-tags').click();
  await page.getByTestId('tag-field-genres').fill('Blasmusik');
  await page.getByTestId('tag-editor-apply').click();
  await expect(page.getByTestId('edit-message')).toContainText('geändert');

  await page.getByTestId('edit-release').click();
  await expect(page.getByTestId('tag-field-title')).toHaveValue('Kassette 1985');
  await page.getByTestId('tag-field-title').fill('Kassette 1986');
  await page.getByTestId('tag-editor-apply').click();
  await expect(page.getByTestId('release-title')).toHaveText('Kassette 1986');

  // The newest change first; undoing it restores the title.
  await page.getByRole('link', { name: 'Einstellungen' }).click();
  const newest = page.locator('[data-testid^="change-"]').first();
  await expect(newest).toContainText('Titel: Kassette 1986');
  await expect(page.locator('[data-testid^="change-"]').nth(1)).toContainText('Genre: Blasmusik');
  await newest.getByRole('button', { name: 'Rückgängig' }).click();
  await expect(page.getByTestId('history-message')).toContainText('rückgängig');
  await expect(page.locator('[data-testid^="change-"]').first()).toContainText('Rückgängig:', {
    timeout: 30_000,
  });

  await page.getByRole('link', { name: 'Lokal' }).click();
  await page
    .locator('[data-testid^="release-"]')
    .filter({ hasText: 'Kassette 1985' })
    .first()
    .click();
  await expect(page.getByTestId('release-title')).toHaveText('Kassette 1985');
});

test('accepting a group in the conflict list', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: /Konflikte/ }).click();
  await expect(page).toHaveURL(/\/conflicts$/);

  // The generated conflicts: " (Remaster)" titles from MusicBrainz for the first two albums.
  const firstGroup = page.locator('[data-testid^="group-"]:not([data-testid="group-all"])').first();
  await expect(firstGroup).toBeVisible();
  await firstGroup.click();
  const rows = page.locator('.conflict-row').filter({ hasText: '(Remaster)' });
  await expect(rows.first()).toBeVisible();
  await page.getByTestId('conflicts-accept-group').click();
  await page.getByTestId('conflicts-confirm').click();
  await expect(page.getByTestId('conflicts-message')).toBeVisible();
  // The group's conflicts are decided: it is empty and leaves the group list.
  await expect(page.getByTestId('conflicts-empty')).toBeVisible({ timeout: 30_000 });
  await page.getByTestId('group-all').click();
  await expect(page.getByTestId('conflicts-total')).not.toContainText('0 Konflikte');
});

test('searching, filtering and opening a result', async ({ page }) => {
  await signIn(page);
  await page.goto('/local/albums');
  await page.getByTestId('search-input').fill('Polka');
  await expect(page).toHaveURL(/\/local\/search\?q=Polka$/);

  // Counts per type first, then the first rows.
  await expect(page.getByTestId('search-count-track')).toHaveText(/^[\d.]+\+?$/);
  await expect(page.getByTestId('search-group-track')).toContainText('Polka');

  // A filter chip narrows the search to albums.
  await page.getByTestId('search-add-filter').click();
  await page.getByTestId('search-filter-field').click();
  await page.getByRole('option', { name: 'Art' }).click();
  await page.getByTestId('search-filter-value').fill('album');
  await page.getByTestId('search-filter-add').click();
  await expect(page.getByTestId('search-input')).toHaveValue('Polka type:album');
  await expect(page.getByTestId('search-chip-type')).toBeVisible();
  await expect(page.getByTestId('search-group-track')).toHaveCount(0);

  const release = page.locator('[data-testid="search-group-release"] [data-testid^="release-"]');
  await expect(release.first()).toBeVisible();
  await release.first().click();
  await expect(page).toHaveURL(/\/local\/releases\//);
  await expect(page.getByTestId('release-title')).toBeVisible();
});

test('playing an imported album, seeking and resuming after a reload', async ({ page }) => {
  await signIn(page);
  await page.goto('/local/albums');
  const kassette = page.locator('[data-testid^="release-"]').filter({ hasText: 'Kassette 1985' });
  await kassette.first().click();
  await expect(page.getByTestId('release-title')).toHaveText('Kassette 1985');

  await page.getByTestId('play-release').click();
  await expect(page.getByTestId('player-title')).toHaveText('Frühling');
  // The browser plays the original: the position moves.
  await expect(page.getByTestId('player-position')).not.toHaveText('0:00', { timeout: 15_000 });
  await expect(page.getByTestId('player-duration')).toHaveText('0:08');

  await page.getByTestId('player-next').click();
  await expect(page.getByTestId('player-title')).toHaveText('Sommer');
  const seek = page.getByTestId('player-seek');
  const box = (await seek.boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.75, box.y + box.height / 2);
  await expect(page.getByTestId('player-position')).toHaveText(/0:0[5-8]/);
  await page.getByTestId('player-toggle').click();
  await expect(page.getByTestId('player-toggle')).toHaveAttribute('aria-label', 'Abspielen');
  const paused = await page.getByTestId('player-position').textContent();

  await page.reload();
  await expect(page.getByTestId('player-title')).toHaveText('Sommer');
  await expect(page.getByTestId('player-position')).toHaveText(paused!);
  await expect(page.getByTestId('player-toggle')).toHaveAttribute('aria-label', 'Abspielen');
});

test('playing a FLAC track at 128 kbit/s while it is being transcoded', async ({ page }) => {
  await signIn(page);
  await page.goto('/settings');
  await page.getByTestId('bitrate-128').click();
  await expect(page.getByTestId('bitrate-message')).toContainText('Gespeichert');

  await page.goto('/local/albums');
  const kassette = page.locator('[data-testid^="release-"]').filter({ hasText: 'Kassette 1985' });
  await kassette.first().click();
  const urls = page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/playback/urls') && response.ok(),
  );
  await page.getByTestId('play-release').click();
  const [current] = (await (await urls).json()) as [{ url: string; transcoded: boolean }];

  // The original is FLAC; this device receives AAC at 128 kbit/s, streamed while it is written.
  expect(current.transcoded).toBe(true);
  expect(current.url).toContain('/media/transcodes/');
  expect(current.url).toContain('aac-128');
  await expect(page.getByTestId('player-title')).toHaveText('Frühling');
  await expect(page.getByTestId('player-position')).not.toHaveText('0:00', { timeout: 15_000 });
  await page.getByTestId('player-toggle').click();

  // Back to the original for the other tests.
  await page.goto('/settings');
  await page.getByTestId('bitrate-original').click();
  await expect(page.getByTestId('bitrate-message')).toContainText('Gespeichert');
});

test('ordering an album from a source and playing a downloaded track', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'Streaming' }).click();

  // The fake source service of the end-to-end server (tools/fake-source-service).
  await expect(page.getByTestId('source-none')).toHaveCount(0, { timeout: 30_000 });
  await page.getByTestId('source-query').fill('https://fake.example/album/2');
  await page.getByTestId('source-submit').click();
  await expect(page.getByTestId('resolved')).toContainText('Bergwind');
  await expect(page.getByTestId('status-track:201')).toContainText('Neu');
  await page.getByTestId('source-order').click();
  await expect(page.getByTestId('source-ordered')).toContainText('2 Titel');

  // The order downloads and enters the library.
  const order = page.locator('[data-testid^="order-"]').filter({ hasText: 'Bergwind' }).first();
  await expect(order).toContainText('Fertig', { timeout: 90_000 });

  await page.goto(`/local/search?q=${encodeURIComponent('Bergwind type:album')}`);
  const release = page.locator('[data-testid="search-group-release"] [data-testid^="release-"]');
  await release.first().click();
  await expect(page.getByTestId('release-title')).toHaveText('Bergwind');
  await expect(page.getByTestId('track-source').first()).toHaveText('FK');
  await page.getByTestId('play-release').click();
  await expect(page.getByTestId('player-title')).toHaveText('Abendrot');
  await expect(page.getByTestId('player-position')).not.toHaveText('0:00', { timeout: 15_000 });
  await page.getByTestId('player-toggle').click();
});
