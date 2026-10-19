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
