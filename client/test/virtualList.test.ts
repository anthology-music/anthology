import type { ClientMessage, ServerMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import { geometry, scrollTopFor } from '@/components/virtualGeometry';

import { json, tokens } from './fakeServer';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

const TOTAL = 500_000;

const item = (position: number) => ({
  id: `item-${position}`,
  key: [`artist ${position}`, `title ${position}`, `item-${position}`],
  artist: `Artist ${position}`,
  title: `Title ${position}`,
  year: 2000,
});

async function demoPage() {
  const services = fakeServices(
    { 'POST /api/v1/auth/refresh': () => json(tokens()) },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/dev/demo', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  // The demo list's subscription (the player subscribes to its state as well).
  const demo = () =>
    socket.sent.find(
      (message): message is Extract<ClientMessage, { type: 'subscribe' }> =>
        message.type === 'subscribe' && message.data.stream === 'demo.items',
    );
  await vi.waitFor(() => expect(demo()).toBeDefined());
  const sub = demo()!.sub;
  const send = (message: ServerMessage) => socket.receive(message);
  return { wrapper, socket, sub, send };
}

function chunk(sub: string, number: number, start: number, count: number): ServerMessage {
  return {
    type: 'chunk',
    sub,
    data: {
      chunk: number,
      start,
      rows: Array.from({ length: count }, (_, index) => item(start + index)),
    },
  };
}

describe('virtual list', () => {
  it('shows the count first, then rows, and skeletons for rows not loaded yet', async () => {
    const { wrapper, sub, send } = await demoPage();

    send({ type: 'snapshot_meta', sub, seq: 1, data: { total: TOTAL, counters: {} } });
    await flushPromises();
    expect(wrapper.find('[data-testid="demo-total"]').text()).toBe('500.000');
    expect(wrapper.findAll('[role="listitem"] .vlist__skeleton').length).toBeGreaterThan(0);

    send(chunk(sub, 0, 0, 5));
    await flushPromises();

    const items = wrapper.findAll('[role="listitem"]');
    expect(items[0]!.text()).toContain('Title 0');
    expect(items[0]!.attributes('aria-posinset')).toBe('1');
    expect(items[0]!.attributes('aria-setsize')).toBe(String(TOTAL));
    expect(items[6]!.find('.vlist__skeleton').exists()).toBe(true);
  });

  it('jumps to row 250,000 and requests that window', async () => {
    const { wrapper, socket, sub, send } = await demoPage();
    send({ type: 'snapshot_meta', sub, seq: 1, data: { total: TOTAL, counters: {} } });
    send(chunk(sub, 0, 0, 100));
    await flushPromises();

    const list = wrapper.find('.vlist');
    const target = scrollTopFor(250_000, 52, geometry(TOTAL, 52, 600));
    (list.element as HTMLElement).scrollTop = target;
    await list.trigger('scroll');
    await vi.waitFor(() => expect(socket.last('window')?.data.start).toBe(249_950));

    send(chunk(sub, 1, 249_950, 100));
    await flushPromises();

    const first = wrapper.find('[role="listitem"]');
    expect(first.attributes('aria-posinset')).toBe('250001');
    expect(first.text()).toContain('Title 250000');
  });

  it('explains how to enable the demo when the server does not offer it', async () => {
    const { wrapper, sub, send } = await demoPage();

    send({ type: 'error', sub, data: { code: 'unknown_stream', message: '' } });
    await flushPromises();

    expect(wrapper.find('[role="alert"]').text()).toContain('ANTHOLOGY_DEV_DEMO=true');
    expect(wrapper.find('.vlist').exists()).toBe(false);
  });
});
