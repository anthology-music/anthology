import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const job = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: ['2026-10-12T08:00:00+00:00', id],
  type: 'demo',
  title: `Job ${id}`,
  status: 'running',
  priority_class: 'background',
  created_by: 'user-1',
  created_by_name: 'Admin',
  created_at: '2026-10-12T08:00:00+00:00',
  started_at: '2026-10-12T08:00:01+00:00',
  finished_at: null,
  total_items: 4,
  done_items: 1,
  failed_items: 0,
  progress: 0.25,
  error: null,
  ...overrides,
});

async function streamingPage(role: 'admin' | 'editor' | 'listener') {
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'POST /api/v1/jobs/a/pause': () => json(job('a', { status: 'paused' })),
      'POST /api/v1/jobs/b/cancel': () => json({ detail: 'forbidden' }, 403),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/streaming', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await vi.waitFor(() => expect(subscription(socket, 'jobs')).toBeDefined());
  return { wrapper, services, socket };
}

function subscription(socket: FakeSocket, stream: string): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === stream,
  );
}

function sendMeta(socket: FakeSocket, sub: string, total: number, counters = {}) {
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total, counters } });
}

function sendRows(socket: FakeSocket, sub: string, rows: object[]) {
  socket.receive({
    type: 'chunk',
    sub,
    data: { chunk: 0, start: 0, rows: rows as Record<string, unknown>[] },
  });
}

const counter = (wrapper: Awaited<ReturnType<typeof streamingPage>>['wrapper'], key: string) =>
  wrapper.find(`[data-testid="job-counter-${key}"]`).text();

describe('jobs view', () => {
  it('shows the counters before any row arrives', async () => {
    const { wrapper, socket } = await streamingPage('admin');
    const sub = subscription(socket, 'jobs')!.sub;

    sendMeta(socket, sub, 7, { queued: 1, paused: 1, running: 2, done: 2, failed: 1 });
    await flushPromises();

    expect(counter(wrapper, 'total')).toBe('7');
    expect(counter(wrapper, 'done')).toBe('2');
    expect(counter(wrapper, 'running')).toBe('2');
    expect(counter(wrapper, 'waiting')).toBe('2');
    expect(counter(wrapper, 'failed')).toBe('1');
    expect(wrapper.findAll('.job-row')).toHaveLength(0);
    expect(wrapper.findAll('.vlist__skeleton').length).toBeGreaterThan(0);
  });

  it('updates the counters from deltas', async () => {
    const { wrapper, socket } = await streamingPage('admin');
    const sub = subscription(socket, 'jobs')!.sub;
    sendMeta(socket, sub, 1, { running: 1 });
    sendRows(socket, sub, [job('a')]);
    await flushPromises();

    socket.receive({
      type: 'delta',
      sub,
      seq: 2,
      data: {
        op: 'upsert',
        id: 'a',
        key: job('a').key,
        row: job('a', { status: 'done', done_items: 4, progress: 1 }),
        total: 1,
        counters: { running: 0, done: 1 },
      },
    });
    await flushPromises();

    expect(counter(wrapper, 'running')).toBe('0');
    expect(counter(wrapper, 'done')).toBe('1');
    expect(wrapper.find('[data-testid="job-a"] .job-status__text').text()).toBe('Fertig');
  });

  it('shows each job with creator, count, progress and status as icon plus text', async () => {
    const { wrapper, socket } = await streamingPage('admin');
    const sub = subscription(socket, 'jobs')!.sub;

    sendMeta(socket, sub, 1, { running: 1 });
    sendRows(socket, sub, [job('a', { created_by_name: 'Lukas' })]);
    await flushPromises();

    const row = wrapper.find('[data-testid="job-a"]');
    expect(row.text()).toContain('Job a');
    expect(row.text()).toContain('von Lukas');
    expect(row.find('[data-testid="job-count"]').text()).toBe('1 / 4');
    expect(row.find('[role="progressbar"]').attributes('aria-valuenow')).toBe('25');
    const status = row.find('.job-status');
    expect(status.text()).toContain('Läuft');
    expect(status.find('.q-icon').exists()).toBe(true);
  });

  it('expands a job to show its items', async () => {
    const { wrapper, socket } = await streamingPage('admin');
    const sub = subscription(socket, 'jobs')!.sub;
    sendMeta(socket, sub, 1, { running: 1 });
    sendRows(socket, sub, [job('a')]);
    await flushPromises();

    await wrapper.find('[data-testid="job-a"] button[aria-expanded="false"]').trigger('click');
    await vi.waitFor(() => expect(subscription(socket, 'job.items')).toBeDefined());
    const items = subscription(socket, 'job.items')!;
    expect(items.data.params).toEqual({ job_id: 'a' });
    sendMeta(socket, items.sub, 2, { done: 1 });
    sendRows(socket, items.sub, [
      { position: 0, title: 'Item 1', status: 'done', progress: 1, outcome: null, message: null },
      {
        position: 1,
        title: 'Item 2',
        status: 'running',
        progress: 0.5,
        outcome: null,
        message: 'halfway',
      },
    ]);
    await flushPromises();

    const panel = wrapper.find('[data-testid="job-items"]');
    expect(panel.text()).toContain('Item 1');
    expect(panel.text()).toContain('halfway');
    expect(panel.text()).toContain('Fertig');

    await wrapper.find('[data-testid="job-a"] button[aria-expanded="true"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="job-items"]').exists()).toBe(false);
    expect(socket.sent.some((m) => m.type === 'unsubscribe' && m.sub === items.sub)).toBe(true);
  });

  it('lets the creator pause their job', async () => {
    const { wrapper, socket, services } = await streamingPage('editor');
    const sub = subscription(socket, 'jobs')!.sub;
    sendMeta(socket, sub, 1, { running: 1 });
    sendRows(socket, sub, [job('a')]);
    await flushPromises();

    const row = wrapper.find('[data-testid="job-a"]');
    expect(row.find('[data-testid="job-resume"]').exists()).toBe(false);
    await row.find('[data-testid="job-pause"]').trigger('click');
    await flushPromises();

    expect(services.server.calls).toContain('POST /api/v1/jobs/a/pause');
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it('hides the controls of other users’ jobs from editors', async () => {
    const { wrapper, socket } = await streamingPage('editor');
    const sub = subscription(socket, 'jobs')!.sub;
    sendMeta(socket, sub, 1, { paused: 1 });
    sendRows(socket, sub, [job('b', { status: 'paused', created_by: 'user-2' })]);
    await flushPromises();

    expect(wrapper.find('[data-testid="job-b"] .job-row__actions button').exists()).toBe(false);
  });

  it('lets admins control every job and shows a refusal of the server', async () => {
    const { wrapper, socket, services } = await streamingPage('admin');
    const sub = subscription(socket, 'jobs')!.sub;
    sendMeta(socket, sub, 1, { paused: 1 });
    sendRows(socket, sub, [job('b', { status: 'paused', created_by: 'user-2' })]);
    await flushPromises();

    const row = wrapper.find('[data-testid="job-b"]');
    expect(row.find('[data-testid="job-resume"]').exists()).toBe(true);
    expect(row.find('[data-testid="job-pause"]').exists()).toBe(false);
    await row.find('[data-testid="job-cancel"]').trigger('click');
    await flushPromises();

    expect(services.server.calls).toContain('POST /api/v1/jobs/b/cancel');
    expect(wrapper.find('[role="alert"]').text()).toContain('Administrator');
  });

  it('offers no controls on finished jobs and no demo button to listeners', async () => {
    const { wrapper, socket } = await streamingPage('listener');
    const sub = subscription(socket, 'jobs')!.sub;
    sendMeta(socket, sub, 1, { done: 1 });
    sendRows(socket, sub, [job('c', { status: 'done', created_by: 'user-1', progress: 1 })]);
    await flushPromises();

    expect(wrapper.find('[data-testid="job-c"] .job-row__actions button').exists()).toBe(false);
    expect(wrapper.find('[data-testid="start-demo-job"]').exists()).toBe(false);
  });

  it('starts a demo job in developer builds', async () => {
    const { wrapper, services } = await streamingPage('editor');
    services.server.calls.length = 0;

    await wrapper.find('[data-testid="start-demo-job"]').trigger('click');
    await flushPromises();

    expect(services.server.calls).toContain('POST /api/v1/dev/jobs/demo');
    expect(wrapper.find('[role="alert"]').text()).toContain('ANTHOLOGY_DEV_DEMO');
  });
});
