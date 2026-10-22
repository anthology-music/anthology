import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const STORAGE = 'storage';

async function settingsPage(
  role: 'admin' | 'editor',
  adoption = () => json({ job_id: 'job-1' }, 202),
) {
  const posted: unknown[] = [];
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
      'POST /api/v1/library/adoption': async (request) => {
        posted.push(await request.json());
        return adoption();
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
  return { wrapper, socket, posted };
}

function subscription(socket: FakeSocket): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === 'library.storage',
  );
}

async function sendStorage(socket: FakeSocket, files: number, bytes: number) {
  await vi.waitFor(() => expect(subscription(socket)).toBeDefined());
  const sub = subscription(socket)!.sub;
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: 1, counters: {} } });
  socket.receive({
    type: 'chunk',
    sub,
    data: {
      chunk: 0,
      start: 0,
      rows: [{ id: STORAGE, key: [STORAGE], referenced_files: files, referenced_bytes: bytes }],
    },
  });
  await flushPromises();
}

function inBody(testId: string): HTMLElement | null {
  return document.body.querySelector(`[data-testid="${testId}"]`);
}

describe('adoption settings', () => {
  it('shows the referenced originals and adopts them after confirmation', async () => {
    const { wrapper, socket, posted } = await settingsPage('admin');
    await sendStorage(socket, 12_000, 480_000_000_000);

    expect(wrapper.find('[data-testid="adoption-summary"]').text()).toMatch(
      /12\.000 Dateien \(480\sGB\)/,
    );
    await wrapper.find('[data-testid="adoption-mode-move"] input').setValue(true);
    await wrapper.find('[data-testid="adoption-start"]').trigger('click');
    await vi.waitFor(() => expect(inBody('adoption-confirm')).not.toBeNull());
    expect(posted).toEqual([]); // nothing before the confirmation
    expect(inBody('adoption-dialog')!.textContent).toContain('Verschieben');

    inBody('adoption-confirm')!.click();
    await vi.waitFor(() => expect(posted).toEqual([{ mode: 'move' }]));
    await flushPromises();
    expect(wrapper.find('[data-testid="adoption-message"]').text()).toContain('läuft als Auftrag');
  });

  it('cannot adopt without referenced originals', async () => {
    const { wrapper, socket } = await settingsPage('admin');
    await sendStorage(socket, 0, 0);

    expect(wrapper.find('[data-testid="adoption-start"]').attributes('disabled')).toBeDefined();
  });

  it('says when an adoption is already running', async () => {
    const { wrapper, socket } = await settingsPage('admin', () =>
      json({ detail: 'adoption_running' }, 409),
    );
    await sendStorage(socket, 3, 3_000);

    await wrapper.find('[data-testid="adoption-start"]').trigger('click');
    await vi.waitFor(() => expect(inBody('adoption-confirm')).not.toBeNull());
    inBody('adoption-confirm')!.click();
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="adoption-message"]').text()).toContain('läuft bereits'),
    );
  });

  it('is only shown to admins', async () => {
    const { wrapper } = await settingsPage('editor');

    expect(wrapper.find('[data-testid="adoption-summary"]').exists()).toBe(false);
  });
});
