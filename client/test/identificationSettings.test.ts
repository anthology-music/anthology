import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const SUMMARY = 'summary';
const summary = (overrides: Record<string, number> = {}) => ({
  id: SUMMARY,
  key: [SUMMARY],
  unchecked: 500_000,
  isrc: 0,
  fingerprint: 0,
  no_match: 0,
  duplicate: 0,
  not_possible: 0,
  ...overrides,
});

const lookupStatus = (overrides: Record<string, unknown> = {}) => ({
  mirror_configured: false,
  mirror_status: null,
  queued_requests: 0,
  estimated_seconds: 0,
  mirror_recommended: false,
  ...overrides,
});

async function settingsPage(
  role: 'admin' | 'editor',
  routes: Record<string, (request: Request) => Response | Promise<Response>> = {},
) {
  const posted: unknown[] = [];
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'GET /api/v1/metadata-lookup/status': () => json(lookupStatus()),
      'POST /api/v1/library/identification': async (request) => {
        posted.push(await request.json());
        return json({ job_id: 'job-1' }, 202);
      },
      ...routes,
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await vi.waitFor(() => expect(subscription(socket)).toBeDefined());
  return { wrapper, socket, posted, services };
}

function subscription(socket: FakeSocket): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === 'library.identification',
  );
}

function sendSummary(socket: FakeSocket, row: object) {
  const sub = subscription(socket)!.sub;
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: 1, counters: {} } });
  socket.receive({
    type: 'chunk',
    sub,
    data: { chunk: 0, start: 0, rows: [row] as Record<string, unknown>[] },
  });
}

const count = (wrapper: Awaited<ReturnType<typeof settingsPage>>['wrapper'], key: string) =>
  wrapper.find(`[data-testid="identification-${key}"] .identification__count`).text();

describe('identification settings', () => {
  it('shows the counts per outcome and follows deltas', async () => {
    const { wrapper, socket } = await settingsPage('editor');
    sendSummary(socket, summary());
    await flushPromises();
    expect(count(wrapper, 'unchecked')).toBe('500.000');

    socket.receive({
      type: 'delta',
      sub: subscription(socket)!.sub,
      seq: 2,
      data: {
        op: 'upsert',
        id: SUMMARY,
        key: [SUMMARY],
        row: summary({ unchecked: 499_999, isrc: 1 }),
        total: 1,
      },
    });
    await flushPromises();

    expect(count(wrapper, 'unchecked')).toBe('499.999');
    expect(count(wrapper, 'isrc')).toBe('1');
  });

  it('starts the identification with the full re-run option', async () => {
    const { wrapper, posted } = await settingsPage('editor');

    await wrapper.find('[data-testid="identification-full"]').trigger('click');
    await wrapper.find('[data-testid="identification-start"]').trigger('click');
    await flushPromises();

    expect(posted).toEqual([{ full: true }]);
    expect(wrapper.find('[data-testid="identification-message"]').text()).toContain(
      'läuft als Auftrag',
    );
  });

  it('says when an identification is already running', async () => {
    const { wrapper } = await settingsPage('editor', {
      'POST /api/v1/library/identification': () => json({ detail: 'identification_running' }, 409),
    });

    await wrapper.find('[data-testid="identification-start"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="identification-message"]').text()).toContain(
      'läuft bereits',
    );
  });

  it('recommends a mirror to admins above 24 hours', async () => {
    const { wrapper } = await settingsPage('admin', {
      'GET /api/v1/metadata-lookup/status': () =>
        json(
          lookupStatus({
            queued_requests: 200_000,
            estimated_seconds: 200_000,
            mirror_recommended: true,
          }),
        ),
    });
    await flushPromises();

    expect(wrapper.find('[data-testid="identification-estimate"]').text()).toContain('2,3 Tage');
    expect(wrapper.find('[data-testid="identification-recommendation"]').exists()).toBe(true);
  });

  it('shows no estimate to editors (admins only)', async () => {
    const { wrapper } = await settingsPage('editor');
    await flushPromises();

    expect(wrapper.find('[data-testid="identification-estimate"]').exists()).toBe(false);
  });
});
