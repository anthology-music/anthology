import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const service = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [0, id],
  name: `Quelle ${id}`,
  source: id,
  short: id.slice(0, 2).toUpperCase(),
  version: '1.0.0',
  available: true,
  problem: null,
  message: null,
  video: false,
  search: true,
  qualities: ['best', 'flac_cd'],
  link_patterns: ['^https://fake\\.example/'],
  login_required: false,
  logged_in: null,
  rate_limited_until: null,
  checked_at: '2026-10-27T10:00:00+00:00',
  ...overrides,
});

const FLAC = {
  format: 'flac',
  lossless: true,
  bitrate_kbps: null,
  sample_rate_hz: 44_100,
  bit_depth: 16,
};

const RESOLVED = {
  service: 'fake',
  item: { ref: 'album:1', kind: 'album', title: 'Polarnacht', artist: 'Nordlicht' },
  tracks: [
    { ref: 'track:101', title: 'Eisfeld', track_number: 1, offered: FLAC, status: 'present' },
    { ref: 'track:102', title: 'Treibeis', track_number: 2, offered: FLAC, status: 'better' },
    { ref: 'track:103', title: 'Driftlinie', track_number: 3, offered: FLAC, status: 'new' },
  ],
};

async function page(path: string, role = 'editor', loginStored = false) {
  const bodies: Record<string, unknown[]> = { search: [], resolve: [], login: [] };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'POST /api/v1/sources/search': async (request) => {
        bodies.search!.push(await request.json());
        return json([
          {
            service: 'fake',
            results: [
              {
                ref: 'album:1',
                kind: 'album',
                title: 'Polarnacht',
                artist: 'Nordlicht',
                year: 2024,
                offered: FLAC,
              },
            ],
            next_page: null,
            error: null,
          },
          { service: 'slow', results: [], next_page: null, error: 'timeout' },
        ]);
      },
      'POST /api/v1/sources/resolve': async (request) => {
        const body = (await request.json()) as { url?: string };
        bodies.resolve!.push(body);
        if (body.url?.includes('elsewhere')) return json({ detail: 'no_source_for_link' }, 422);
        return json(RESOLVED);
      },
      'GET /api/v1/sources/services/tidal/login': () =>
        json({
          fields: [
            { name: 'username', label: 'Benutzername', secret: false },
            { name: 'password', label: 'Passwort', secret: true },
          ],
          stored: loginStored,
          stored_fields: loginStored ? ['password', 'username'] : [],
          logged_in: false,
          problem: 'login_missing',
        }),
      'PUT /api/v1/sources/services/tidal/login': async (request) => {
        bodies.login!.push(await request.json());
        return json({
          fields: [
            { name: 'username', label: 'Benutzername', secret: false },
            { name: 'password', label: 'Passwort', secret: true },
          ],
          stored: true,
          stored_fields: ['password', 'username'],
          logged_in: true,
          problem: null,
        });
      },
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path, guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, bodies };
}

async function serveServices(socket: FakeSocket, rows: Record<string, unknown>[]) {
  const sub = () =>
    socket.sent.find(
      (message): message is Subscribe =>
        message.type === 'subscribe' && message.data.stream === 'sources.services',
    );
  await vi.waitFor(() => expect(sub()).toBeDefined());
  const { sub: id } = sub()!;
  socket.receive({
    type: 'snapshot_meta',
    sub: id,
    seq: 1,
    data: { total: rows.length, counters: {} },
  });
  socket.receive({ type: 'chunk', sub: id, data: { chunk: 0, start: 0, rows } });
  await flushPromises();
}

const unavailable = service('tidal', {
  name: 'Tidal',
  available: false,
  problem: 'incompatible',
  login_required: true,
  logged_in: false,
});

describe('sources', () => {
  it('searches the available sources and shows the tracks with their duplicate status', async () => {
    const { wrapper, socket, bodies } = await page('/streaming');
    await serveServices(socket, [service('fake', { name: 'Fake' }), unavailable]);

    // Only the available source is offered, without a reason for the other.
    expect(wrapper.find('[data-testid="source-fake"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="source-tidal"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Inkompatible Version');

    await wrapper.find('[data-testid="source-query"]').setValue('polar');
    await wrapper.find('.source-search__form').trigger('submit');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="result-album:1"]').exists()).toBe(true),
    );
    expect(bodies.search![0]).toMatchObject({ query: 'polar', service: null });
    expect(wrapper.find('[data-testid="source-results"]').text()).toContain('keine Antwort');
    expect(wrapper.find('[data-testid="result-album:1"]').text()).toContain('FLAC 16/44.1');

    await wrapper.find('[data-testid="open-album:1"]').trigger('click');
    await vi.waitFor(() => expect(wrapper.find('[data-testid="resolved"]').exists()).toBe(true));
    expect(bodies.resolve![0]).toEqual({ service: 'fake', ref: 'album:1' });
    expect(wrapper.find('[data-testid="status-track:101"]').text()).toContain('Schon vorhanden');
    expect(wrapper.find('[data-testid="status-track:102"]').text()).toContain('Besseres Angebot');
    expect(wrapper.find('[data-testid="status-track:103"]').text()).toContain('Neu');
    // Present tracks start unselected.
    expect(wrapper.find('[data-testid="resolved-selected"]').text()).toContain('2 ausgewählt');
  });

  it('opens links and reports links no source can open', async () => {
    const { wrapper, socket, bodies } = await page('/streaming');
    await serveServices(socket, [service('fake')]);

    await wrapper.find('[data-testid="source-query"]').setValue('https://elsewhere/album/1');
    expect(wrapper.find('[data-testid="source-submit"]').text()).toContain('Link öffnen');
    await wrapper.find('.source-search__form').trigger('submit');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="source-error"]').text()).toContain(
        'Keine verfügbare Quelle',
      ),
    );
    await wrapper.find('[data-testid="source-query"]').setValue('https://fake.example/album/1');
    await wrapper.find('.source-search__form').trigger('submit');
    await vi.waitFor(() => expect(wrapper.find('[data-testid="resolved"]').exists()).toBe(true));

    expect(bodies.resolve).toEqual([
      { url: 'https://elsewhere/album/1' },
      { url: 'https://fake.example/album/1' },
    ]);
  });

  it('shows every user why a source is missing, only in the opened status', async () => {
    const { wrapper, socket } = await page('/streaming', 'listener');
    await serveServices(socket, [service('fake', { name: 'Fake' }), unavailable]);

    expect(wrapper.find('[data-testid="source-query"]').exists()).toBe(false);
    expect(document.body.textContent).not.toContain('Inkompatible Version');
    await wrapper.find('[data-testid="source-status-open"]').trigger('click');
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="source-status-tidal"]')).not.toBeNull(),
    );

    expect(
      document.body.querySelector('[data-testid="source-status-tidal"]')!.textContent,
    ).toContain('Inkompatible Version');
    expect(
      document.body.querySelector('[data-testid="source-status-fake"]')!.textContent,
    ).toContain('Verfügbar');
  });

  it('shows stored login fields masked and changes only what is entered', async () => {
    const { wrapper, socket, bodies } = await page('/settings', 'admin', true);
    await serveServices(socket, [unavailable]);

    // Stored fields appear masked at once, never with their values.
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="login-tidal-password"]').exists()).toBe(true),
    );
    for (const name of ['username', 'password']) {
      const input = wrapper.find(`[data-testid="login-tidal-${name}"]`);
      expect((input.element as HTMLInputElement).value).toBe('••••••••');
      expect(input.attributes('readonly')).toBeDefined();
      expect(input.attributes('type')).toBe('password');
    }
    expect(wrapper.find('[data-testid="source-settings-tidal"]').text()).toContain('Gespeichert');

    await wrapper.find('[data-testid="login-change-tidal"]').trigger('click');
    const password = wrapper.find('[data-testid="login-tidal-password"]');
    expect((password.element as HTMLInputElement).value).toBe('');
    expect(password.attributes('placeholder')).toContain('Leer lassen');
    await password.setValue('neu');
    await wrapper.find('.source-settings__login').trigger('submit');
    await vi.waitFor(() => expect(bodies.login).toHaveLength(1));

    // The empty user name keeps its stored value on the server.
    expect(bodies.login![0]).toEqual({ fields: { username: '', password: 'neu' } });
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="login-message-tidal"]').text()).toContain('Angemeldet'),
    );
    expect(
      (wrapper.find('[data-testid="login-tidal-password"]').element as HTMLInputElement).value,
    ).toBe('••••••••');
  });
});
