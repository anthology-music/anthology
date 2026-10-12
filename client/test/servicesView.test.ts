import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import App from '@/App.vue';
import { useServiceAvailable } from '@/sync/services';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const tagger = (status: string, overrides: Record<string, unknown> = {}) => ({
  id: 'service-tagger',
  key: ['tagger'],
  name: 'tagger',
  status,
  version: '0.1.0',
  interface: '1.0',
  message: null,
  changed_at: '2026-10-12T08:00:00+00:00',
  ...overrides,
});

async function connected(role: 'admin' | 'editor', component = App, path = '/settings') {
  const services = fakeServices(
    { 'POST /api/v1/auth/refresh': () => json(tokens({ role })) },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(component, { path, guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket };
}

function servicesSub(socket: FakeSocket): string | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === 'services',
  )?.sub;
}

function snapshot(socket: FakeSocket, sub: string, rows: object[]) {
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

describe('service status', () => {
  it('shows admins each service with status as icon plus text and versions', async () => {
    const { wrapper, socket } = await connected('admin');
    await vi.waitFor(() => expect(servicesSub(socket)).toBeDefined());
    const sub = servicesSub(socket)!;

    snapshot(socket, sub, [tagger('available')]);
    await flushPromises();

    const row = wrapper.find('[data-testid="service-tagger"]');
    expect(row.text()).toContain('Tagger');
    expect(row.text()).toContain('Version 0.1.0 · Schnittstelle 1.0');
    expect(row.find('.service-status__text').text()).toBe('Verfügbar');
    expect(row.find('.service-status .q-icon').exists()).toBe(true);
  });

  it('follows status changes live', async () => {
    const { wrapper, socket } = await connected('admin');
    await vi.waitFor(() => expect(servicesSub(socket)).toBeDefined());
    const sub = servicesSub(socket)!;
    snapshot(socket, sub, [tagger('available')]);
    await flushPromises();

    socket.receive({
      type: 'delta',
      sub,
      seq: 2,
      data: {
        op: 'upsert',
        id: 'service-tagger',
        key: ['tagger'],
        row: tagger('unavailable', { version: null, interface: null, message: 'refused' }),
        total: 1,
        counters: { available: 0, unavailable: 1, incompatible: 0 },
      },
    });
    await flushPromises();

    const row = wrapper.find('[data-testid="service-tagger"]');
    expect(row.find('.service-status__text').text()).toBe('Nicht erreichbar');
    expect(row.text()).toContain('refused');
  });

  it('is not shown to editors', async () => {
    const { wrapper } = await connected('editor');

    expect(wrapper.find('#services-title').exists()).toBe(false);
  });

  it('tells features whether a service is available', async () => {
    const Probe = defineComponent({
      setup() {
        const available = useServiceAvailable('tagger');
        return () => h('span', { 'data-testid': 'probe' }, String(available.value));
      },
    });
    const { wrapper, socket } = await connected('editor', Probe, '/local');
    await vi.waitFor(() => expect(servicesSub(socket)).toBeDefined());
    const sub = servicesSub(socket)!;

    expect(wrapper.find('[data-testid="probe"]').text()).toBe('false');
    snapshot(socket, sub, [tagger('available')]);
    await flushPromises();
    expect(wrapper.find('[data-testid="probe"]').text()).toBe('true');
  });
});
