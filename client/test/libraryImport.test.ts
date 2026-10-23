import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const ROOT = '/data/imports';
const FOLDER = `${ROOT}/Vinyl Rips`;
const empty = { files: 0, bytes: 0 };

const report = (overrides: Record<string, unknown> = {}) => ({
  categories: {
    new: { files: 1200, bytes: 40_000_000_000 },
    replaces_lower_quality: { files: 0, bytes: 0 },
    suspicious_quality: { files: 0, bytes: 0 },
    already_present: { files: 30, bytes: 900_000_000 },
    duplicate_in_source: { files: 4, bytes: 120_000_000 },
    needs_review: empty,
    broken: { files: 2, bytes: 1_000 },
    skipped: empty,
  },
  files: 1236,
  bytes: 41_020_001_000,
  adds_bytes: 40_000_000_000,
  managed: true,
  imported: 0,
  failed: empty,
  ...overrides,
});

const importRow = (overrides: Record<string, unknown> = {}) => ({
  id: 'import-1',
  key: ['2026-10-22T08:00:00+00:00', 'import-1'],
  source_path: FOLDER,
  mode: 'copy',
  managed: true,
  allow_tag_writes: false,
  delete_replaced: true,
  status: 'reported',
  report: report(),
  job_id: null,
  error: null,
  created_at: '2026-10-22T08:00:00+00:00',
  finished_at: null,
  ...overrides,
});

const listing = (path: string | null, modes: string[] | null = null) => ({
  path,
  parent: path === FOLDER ? ROOT : null,
  folders:
    path === null
      ? [{ name: 'imports', path: ROOT }]
      : path === ROOT
        ? [{ name: 'Vinyl Rips', path: FOLDER }]
        : [],
  modes,
  default_mode: modes ? (modes.includes('hardlink') ? 'hardlink' : 'copy') : null,
});

async function streamingPage(
  role: 'admin' | 'editor',
  modes: string[] = ['reference', 'copy', 'move'],
) {
  const calls: { route: string; body?: unknown }[] = [];
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'GET /api/v1/library-import/folders': (request) => {
        const path = new URL(request.url).searchParams.get('path');
        return json(listing(path, path && path !== ROOT ? modes : path ? ['reference'] : null));
      },
      'POST /api/v1/library-imports': async (request) => {
        calls.push({ route: 'start', body: await request.json() });
        return json({ import_id: 'import-2', job_id: 'job-1' }, 202);
      },
      'POST /api/v1/library-imports/import-1/confirm': () => {
        calls.push({ route: 'confirm' });
        return json({ import_id: 'import-1', job_id: 'job-2' }, 202);
      },
      'POST /api/v1/library-imports/import-1/cancel': () => {
        calls.push({ route: 'cancel' });
        return json({ import_id: 'import-1', job_id: null });
      },
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/streaming', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await vi.waitFor(() => expect(subscription(socket, 'jobs')).toBeDefined());
  return { wrapper, socket, calls };
}

function subscription(socket: FakeSocket, stream: string): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === stream,
  );
}

function sendImports(socket: FakeSocket, rows: object[]) {
  const sub = subscription(socket, 'library_import.imports')!.sub;
  socket.receive({
    type: 'snapshot_meta',
    sub,
    seq: 1,
    data: { total: rows.length, counters: {} },
  });
  socket.receive({
    type: 'chunk',
    sub,
    data: { chunk: 0, start: 0, rows: rows as Record<string, unknown>[] },
  });
}

/** The dialog is teleported to the document body. */
function inBody(testId: string): HTMLElement | null {
  return document.body.querySelector(`[data-testid="${testId}"]`);
}

async function openDialogAt(wrapper: Awaited<ReturnType<typeof streamingPage>>['wrapper']) {
  await wrapper.find('[data-testid="import-folder"]').trigger('click');
  await vi.waitFor(() => expect(inBody('import-folder-imports')).not.toBeNull());
  inBody('import-folder-imports')!.click();
  await vi.waitFor(() => expect(inBody('import-folder-Vinyl Rips')).not.toBeNull());
  inBody('import-folder-Vinyl Rips')!.click();
  await vi.waitFor(() => expect(inBody('import-mode-copy')).not.toBeNull());
}

describe('library import', () => {
  it('renders the report from the stream and follows deltas', async () => {
    const { wrapper, socket } = await streamingPage('admin');
    await vi.waitFor(() => expect(subscription(socket, 'library_import.imports')).toBeDefined());
    sendImports(socket, [importRow()]);
    await flushPromises();

    await wrapper.find('[data-testid="import-import-1"] button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="import-category-new"]').text()).toContain('1.200 Dateien');
    // Intl separates number and unit with a no-break space.
    expect(wrapper.find('[data-testid="import-category-new"]').text()).toMatch(/40\sGB/);
    expect(wrapper.find('[data-testid="import-adds"]').text()).toMatch(/40\sGB/);
    expect(wrapper.find('[data-testid="import-managed"]').text()).toContain('verwaltet');

    socket.receive({
      type: 'delta',
      sub: subscription(socket, 'library_import.imports')!.sub,
      seq: 2,
      data: {
        op: 'upsert',
        id: 'import-1',
        key: importRow().key,
        row: importRow({ status: 'done', report: report({ imported: 1234 }) }),
        total: 1,
      },
    });
    await flushPromises();

    expect(wrapper.find('[data-testid="import-status"]').text()).toContain('Fertig');
    expect(wrapper.find('[data-testid="import-result"]').text()).toContain('1.234');
    expect(wrapper.find('[data-testid="import-confirm"]').exists()).toBe(false);
  });

  it('confirms and cancels a report over the API', async () => {
    const { wrapper, socket, calls } = await streamingPage('admin');
    await vi.waitFor(() => expect(subscription(socket, 'library_import.imports')).toBeDefined());
    sendImports(socket, [importRow({ mode: 'reference', managed: false })]);
    await flushPromises();
    await wrapper.find('[data-testid="import-import-1"] button').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="import-managed"]').text()).toContain('referenziert');
    await wrapper.find('[data-testid="import-confirm"]').trigger('click');
    await wrapper.find('[data-testid="import-cancel"]').trigger('click');
    await flushPromises();

    expect(calls.map((call) => call.route)).toEqual(['confirm', 'cancel']);
  });

  it('starts a scan from the folder dialog with the chosen mode', async () => {
    const { wrapper, calls } = await streamingPage('admin', [
      'reference',
      'copy',
      'move',
      'hardlink',
    ]);
    await openDialogAt(wrapper);

    // The proposed mode is preselected; tag writes are offered for referenced modes only.
    expect(
      (inBody('import-mode-hardlink')!.querySelector('input') as HTMLInputElement).checked,
    ).toBe(true);
    expect(inBody('import-tag-writes')).not.toBeNull();
    inBody('import-mode-copy')!.querySelector('input')!.click();
    await flushPromises();
    expect(inBody('import-tag-writes')).toBeNull();

    inBody('import-scan')!.click();
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({
      route: 'start',
      body: { path: FOLDER, mode: 'copy', allow_tag_writes: false, delete_replaced: true },
    });
  });

  it('keeps replaced originals when the deletion option is unchecked', async () => {
    const { wrapper, calls } = await streamingPage('admin');
    await openDialogAt(wrapper);

    // Checked by default (ADR 0021).
    const option = inBody('import-delete-replaced')!;
    expect(option.getAttribute('aria-checked')).toBe('true');
    option.click();
    await flushPromises();
    inBody('import-scan')!.click();
    await vi.waitFor(() => expect(calls).toHaveLength(1));

    expect(calls[0]!.body).toMatchObject({ delete_replaced: false });
  });

  it('states replacements and the deletion option in the report', async () => {
    const { wrapper, socket } = await streamingPage('admin');
    await vi.waitFor(() => expect(subscription(socket, 'library_import.imports')).toBeDefined());
    const categories = {
      ...report().categories,
      replaces_lower_quality: { files: 3, bytes: 90_000_000 },
      suspicious_quality: { files: 2, bytes: 60_000_000 },
    };
    sendImports(socket, [importRow({ delete_replaced: false, report: report({ categories }) })]);
    await flushPromises();
    await wrapper.find('[data-testid="import-import-1"] button').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="import-category-replaces_lower_quality"]').text()).toContain(
      '3 Dateien',
    );
    expect(wrapper.find('[data-testid="import-category-suspicious_quality"]').text()).toContain(
      '2 Dateien',
    );
    expect(wrapper.find('[data-testid="import-replaced"]').text()).toContain('bleiben im Bericht');
  });

  it('hides link modes the folder does not allow', async () => {
    const { wrapper } = await streamingPage('admin', ['reference', 'copy', 'move']);
    await openDialogAt(wrapper);

    expect(inBody('import-mode-hardlink')).toBeNull();
    expect(inBody('import-mode-reflink')).toBeNull();
    expect((inBody('import-mode-copy')!.querySelector('input') as HTMLInputElement).checked).toBe(
      true,
    );
  });

  it('is only offered to admins', async () => {
    const { wrapper } = await streamingPage('editor');

    expect(wrapper.find('[data-testid="import-folder"]').exists()).toBe(false);
  });
});
