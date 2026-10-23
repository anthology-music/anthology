import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const DEFAULTS = {
  enabled: true,
  frequency: 'daily',
  time: '03:00',
  weekday: null,
  options: { action: 'delete', grace_hours: 24, safety_share_percent: 1 },
  next_run_at: '2026-10-24T01:00:00+00:00',
  time_zone: 'Europe/Berlin',
};

const runRow = (overrides: Record<string, unknown> = {}) => ({
  id: 'run-1',
  key: ['2026-10-23T01:00:00+00:00', 'run-1'],
  job_id: 'job-1',
  trigger: 'schedule',
  status: 'done',
  action: 'delete',
  grace_hours: 24,
  safety_share_percent: 1,
  safety_limit: 500,
  managed_files: 50_000,
  started_at: '2026-10-23T01:00:00+00:00',
  finished_at: '2026-10-23T01:05:00+00:00',
  error: null,
  orphan_files: 2,
  orphan_bytes: 8_000_000,
  leftover_files: 1,
  leftover_bytes: 1_000,
  missing_files: 1,
  missing_bytes: 30_000_000,
  deleted_files: 3,
  deleted_bytes: 8_001_000,
  listed_files: 0,
  listed_bytes: 0,
  ...overrides,
});

const findingRow = (id: string, kind: string, outcome: string) => ({
  id,
  key: [`/data/library/_originals/ab/${id}.flac`],
  path: `/data/library/_originals/ab/${id}.flac`,
  kind,
  size_bytes: 4_000_000,
  modified_at: '2026-10-20T10:00:00+00:00',
  outcome,
  detail: null,
});

interface Calls {
  put: unknown[];
  runs: number;
  confirmed: string[];
}

async function settingsPage(role: 'admin' | 'editor' = 'admin', runStatus = 202) {
  const calls: Calls = { put: [], runs: 0, confirmed: [] };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'GET /api/v1/metadata-lookup/status': () =>
        json({
          mirror_configured: false,
          mirror_status: null,
          queued_requests: 0,
          estimated_seconds: 0,
          mirror_recommended: false,
        }),
      'GET /api/v1/maintenance/schedule': () => json(DEFAULTS),
      'PUT /api/v1/maintenance/schedule': async (request) => {
        const body = (await request.json()) as Record<string, unknown>;
        calls.put.push(body);
        return json({ ...body, next_run_at: '2026-10-25T03:00:00+00:00', time_zone: 'UTC' });
      },
      'POST /api/v1/maintenance/runs': () => {
        calls.runs += 1;
        return runStatus === 202
          ? json({ job_id: 'job-2' }, 202)
          : json({ detail: 'maintenance_running' }, runStatus);
      },
      'POST /api/v1/maintenance/runs/run-1/confirm': () => {
        calls.confirmed.push('run-1');
        return json({ job_id: 'job-3' }, 202);
      },
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, calls };
}

function subscription(socket: FakeSocket, stream: string): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === stream,
  );
}

async function sendRun(
  socket: FakeSocket,
  row: ReturnType<typeof runRow>,
  findings: ReturnType<typeof findingRow>[],
) {
  await vi.waitFor(() => expect(subscription(socket, 'library.maintenance')).toBeDefined());
  const sub = subscription(socket, 'library.maintenance')!.sub;
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: 1, counters: {} } });
  socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows: [row] } });
  await flushPromises();
  if (!findings.length) return;
  await vi.waitFor(() =>
    expect(subscription(socket, 'library.maintenance.findings')).toBeDefined(),
  );
  const findingsSub = subscription(socket, 'library.maintenance.findings')!;
  expect(findingsSub.data.params).toEqual({ run_id: row.id });
  socket.receive({
    type: 'snapshot_meta',
    sub: findingsSub.sub,
    seq: 2,
    data: { total: findings.length, counters: {} },
  });
  socket.receive({
    type: 'chunk',
    sub: findingsSub.sub,
    data: { chunk: 0, start: 0, rows: findings },
  });
  await flushPromises();
}

const inBody = (testId: string) => document.body.querySelector(`[data-testid="${testId}"]`);

describe('system maintenance', () => {
  it('shows the defaults and saves a weekly schedule with its options', async () => {
    const { wrapper, calls } = await settingsPage();
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="maintenance-form"]').exists()).toBe(true),
    );

    expect(wrapper.find<HTMLInputElement>('[data-testid="maintenance-time"]').element.value).toBe(
      '03:00',
    );
    expect(wrapper.find('[data-testid="maintenance-next"]').text()).toContain('Europe/Berlin');

    await wrapper.find('[data-testid="maintenance-frequency-weekly"] input').setValue(true);
    await wrapper.find('[data-testid="maintenance-weekday"]').setValue('6');
    await wrapper.find('[data-testid="maintenance-time"]').setValue('04:00');
    await wrapper.find('[data-testid="maintenance-action-report"] input').setValue(true);
    await wrapper.find('[data-testid="maintenance-grace"]').setValue('48');
    await wrapper.find('[data-testid="maintenance-safety-on"]').setValue(false);
    await wrapper.find('[data-testid="maintenance-form"]').trigger('submit');
    await vi.waitFor(() => expect(calls.put).toHaveLength(1));
    await flushPromises();

    expect(calls.put[0]).toEqual({
      enabled: true,
      frequency: 'weekly',
      time: '04:00',
      weekday: 6,
      options: { action: 'report', grace_hours: 48, safety_share_percent: null },
    });
    expect(wrapper.find('[data-testid="maintenance-next"]').text()).toContain('Sonntag');
    expect(wrapper.find('[data-testid="maintenance-message"]').text()).toContain('nächsten Lauf');
  });

  it('switches the schedule off and refuses an invalid grace period', async () => {
    const { wrapper, calls } = await settingsPage();
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="maintenance-form"]').exists()).toBe(true),
    );

    await wrapper.find('[data-testid="maintenance-grace"]').setValue('200');
    await wrapper.find('[data-testid="maintenance-form"]').trigger('submit');
    await flushPromises();
    expect(calls.put).toEqual([]);
    expect(wrapper.find('[data-testid="maintenance-message"]').text()).toContain('Eingaben');

    await wrapper.find('[data-testid="maintenance-grace"]').setValue('24');
    await wrapper.find('[data-testid="maintenance-frequency-off"] input').setValue(true);
    await wrapper.find('[data-testid="maintenance-form"]').trigger('submit');
    await vi.waitFor(() => expect(calls.put).toHaveLength(1));
    expect(calls.put[0]).toMatchObject({ enabled: false, frequency: 'daily', weekday: null });
  });

  it('shows the last result with its files', async () => {
    const { wrapper, socket } = await settingsPage();
    await sendRun(socket, runRow(), [
      findingRow('a', 'orphan', 'deleted'),
      findingRow('b', 'missing', 'listed'),
    ]);

    expect(wrapper.find('[data-testid="maintenance-status"]').text()).toContain('Abgeschlossen');
    expect(wrapper.find('[data-testid="maintenance-deleted"]').text()).toMatch(
      /3 Dateien \(8\sMB\)/,
    );
    expect(wrapper.find('[data-testid="maintenance-missing"]').text()).toMatch(
      /1 Datei \(30\sMB\)/,
    );
    expect(wrapper.find('[data-testid="finding-a"]').text()).toContain('Verwaist');
    expect(wrapper.find('[data-testid="finding-outcome-a"]').text()).toContain('Gelöscht');
    expect(wrapper.find('[data-testid="finding-b"]').text()).toContain('Fehlt');
  });

  it('runs now and shows an active run', async () => {
    const { wrapper, socket, calls } = await settingsPage();
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="maintenance-run"]').exists()).toBe(true),
    );

    await wrapper.find('[data-testid="maintenance-run"]').trigger('click');
    await vi.waitFor(() => expect(calls.runs).toBe(1));
    await flushPromises();
    expect(wrapper.find('[data-testid="maintenance-message"]').text()).toContain('Auftrag');

    await sendRun(socket, runRow({ status: 'running', finished_at: null }), []);
    const button = wrapper.find('[data-testid="maintenance-run"]');
    expect(button.text()).toContain('Ein Lauf ist aktiv');
    expect(button.attributes('disabled')).toBeDefined();
  });

  it('reports a run already active', async () => {
    const { wrapper, calls } = await settingsPage('admin', 409);
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="maintenance-run"]').exists()).toBe(true),
    );

    await wrapper.find('[data-testid="maintenance-run"]').trigger('click');
    await vi.waitFor(() => expect(calls.runs).toBe(1));
    await flushPromises();

    expect(wrapper.find('[data-testid="maintenance-message"]').text()).toContain('bereits aktiv');
  });

  it('confirms the deletion of a run held by the safety limit', async () => {
    const { wrapper, socket, calls } = await settingsPage();
    await sendRun(
      socket,
      runRow({
        status: 'held',
        orphan_files: 5_000,
        orphan_bytes: 5_000_000_000,
        deleted_files: 0,
        deleted_bytes: 0,
        listed_files: 5_000,
        listed_bytes: 5_000_000_000,
      }),
      [findingRow('a', 'orphan', 'listed')],
    );

    expect(wrapper.find('[data-testid="maintenance-status"]').text()).toContain('Bestätigung');
    expect(wrapper.find('[data-testid="maintenance-held"]').text()).toContain('500');
    await wrapper.find('[data-testid="maintenance-confirm-open"]').trigger('click');
    await vi.waitFor(() => expect(inBody('maintenance-confirm')).not.toBeNull());
    expect(calls.confirmed).toEqual([]); // nothing before the confirmation
    (inBody('maintenance-confirm') as HTMLElement).click();
    await vi.waitFor(() => expect(calls.confirmed).toEqual(['run-1']));
  });

  it('is only shown to admins', async () => {
    const { wrapper, socket } = await settingsPage('editor');

    expect(wrapper.find('[data-testid="maintenance-form"]').exists()).toBe(false);
    expect(subscription(socket, 'library.maintenance')).toBeUndefined();
  });
});
