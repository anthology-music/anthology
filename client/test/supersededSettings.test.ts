import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const fileRow = (id: string, mode: 'managed' | 'referenced') => ({
  id,
  key: [`/data/${id}.flac`, id],
  path: `/data/${id}.flac`,
  size_bytes: 30_000_000,
  format: 'mp3',
  storage_mode: mode,
  recording_id: `recording-${id}`,
  title: 'Eisfeld',
  artist: 'Nordlicht',
  superseded_at: '2026-10-23T08:00:00+00:00',
  replaced_by_id: 'new',
  replaced_by_path: '/data/new.flac',
});

async function settingsPage(role: 'admin' | 'editor' = 'admin') {
  const posted: string[] = [];
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
      'POST /api/v1/library/superseded/deletion': () => {
        posted.push('deletion');
        return json({ job_id: 'job-1' }, 202);
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
      message.type === 'subscribe' && message.data.stream === 'library.superseded',
  );
}

async function sendReport(socket: FakeSocket) {
  await vi.waitFor(() => expect(subscription(socket)).toBeDefined());
  const sub = subscription(socket)!.sub;
  socket.receive({
    type: 'snapshot_meta',
    sub,
    seq: 1,
    data: {
      total: 2,
      counters: {
        superseded_files: 2,
        superseded_bytes: 60_000_000,
        superseded_managed_files: 1,
        superseded_managed_bytes: 30_000_000,
      },
    },
  });
  socket.receive({
    type: 'chunk',
    sub,
    data: { chunk: 0, start: 0, rows: [fileRow('a', 'managed'), fileRow('b', 'referenced')] },
  });
  await flushPromises();
}

const inBody = (testId: string) => document.body.querySelector(`[data-testid="${testId}"]`);

describe('replaced originals', () => {
  it('shows managed and referenced files and deletes managed ones after confirmation', async () => {
    const { wrapper, socket, posted } = await settingsPage();
    await sendReport(socket);

    expect(wrapper.find('[data-testid="superseded-managed"]').text()).toMatch(/1 Datei \(30\sMB\)/);
    expect(wrapper.find('[data-testid="superseded-referenced"]').text()).toContain('nie gelöscht');
    expect(wrapper.find('[data-testid="superseded-mode-a"]').text()).toContain('Verwaltet');
    expect(wrapper.find('[data-testid="superseded-mode-b"]').text()).toContain('Referenziert');

    await wrapper.find('[data-testid="superseded-delete"]').trigger('click');
    await vi.waitFor(() => expect(inBody('superseded-confirm')).not.toBeNull());
    expect(posted).toEqual([]); // nothing before the confirmation
    (inBody('superseded-confirm') as HTMLElement).click();
    await vi.waitFor(() => expect(posted).toEqual(['deletion']));
    await flushPromises();

    expect(wrapper.find('[data-testid="superseded-message"]').text()).toContain('Auftrag');
  });

  it('is only shown to admins', async () => {
    const { wrapper } = await settingsPage('editor');
    expect(wrapper.find('[data-testid="superseded-managed"]').exists()).toBe(false);
  });
});
