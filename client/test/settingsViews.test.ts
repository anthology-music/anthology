import type { ClientMessage, ServerMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

const device = (id: string, name: string, current = false) => ({
  id,
  key: [name, id],
  name,
  type: 'desktop',
  platform: 'linux',
  signed_in_at: '2026-10-12T08:00:00+00:00',
  last_used_at: '2026-10-12T09:30:00+00:00',
  current,
});

/** Answer the subscriptions of the open socket like the server would. */
function serve(socket: FakeSocket, streams: Record<string, object[]>) {
  const answered = new Set<string>();
  return () => {
    for (const message of socket.sent) {
      if (message.type !== 'subscribe' || answered.has(message.sub)) continue;
      answered.add(message.sub);
      const rows = streams[message.data.stream] ?? [];
      const send = (reply: ServerMessage) => socket.receive(reply);
      send({
        type: 'snapshot_meta',
        sub: message.sub,
        seq: 1,
        data: { total: rows.length, counters: {} },
      });
      send({
        type: 'chunk',
        sub: message.sub,
        data: { chunk: 0, start: 0, rows: rows as Record<string, unknown>[] },
      });
    }
  };
}

async function signedInApp(role: 'admin' | 'listener', streams: Record<string, object[]>) {
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'DELETE /api/v1/me/devices/phone': () => new Response(null, { status: 204 }),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  const answer = serve(socket, streams);
  await vi.waitFor(() => {
    answer();
    expect(socket.sent.some((message: ClientMessage) => message.type === 'subscribe')).toBe(true);
  });
  answer();
  await flushPromises();
  return { wrapper, services, socket };
}

describe('settings views', () => {
  it('lists my devices with the current one marked', async () => {
    const { wrapper } = await signedInApp('listener', {
      'me.devices': [device('laptop', 'Laptop', true), device('phone', 'Phone')],
    });

    await vi.waitFor(() => expect(wrapper.findAll('#my-devices-title ~ ul li')).toHaveLength(2));
    const rows = wrapper.findAll('#my-devices-title ~ ul li').map((row) => row.text());
    expect(rows[0]).toContain('Laptop');
    expect(rows[0]).toContain('Dieses Gerät');
    expect(rows[1]).toContain('Phone');
  });

  it('signs out another device through the API', async () => {
    const { wrapper, services } = await signedInApp('listener', {
      'me.devices': [device('laptop', 'Laptop', true), device('phone', 'Phone')],
    });
    await vi.waitFor(() =>
      expect(wrapper.find('button[aria-label="Phone abmelden"]').exists()).toBe(true),
    );

    await wrapper.find('button[aria-label="Phone abmelden"]').trigger('click');
    await flushPromises();

    expect(services.server.calls).toContain('DELETE /api/v1/me/devices/phone');
  });

  it('shows the account administration only to admins', async () => {
    const listener = await signedInApp('listener', { 'me.devices': [] });
    expect(listener.wrapper.find('#users-title').exists()).toBe(false);

    const admin = await signedInApp('admin', {
      'me.devices': [],
      users: [
        {
          id: 'user-1',
          key: ['admin', 'user-1'],
          username: 'admin',
          display_name: 'Admin',
          role: 'admin',
          active: true,
        },
      ],
    });
    await vi.waitFor(() => expect(admin.wrapper.find('#users-title').exists()).toBe(true));
    expect(admin.wrapper.find('#users-title').text()).toContain('Konten');
  });

  it('shows the live connection and the signed-in user in the navigation', async () => {
    const { wrapper } = await signedInApp('admin', { 'me.devices': [], users: [] });

    await vi.waitFor(() => expect(wrapper.find('[role="status"]').text()).toBe('Verbunden · live'));
    expect(wrapper.find('.sidebar__user').text()).toContain('Admin');
    expect(wrapper.find('.sidebar__user').text()).toContain('Administrator');
  });
});
