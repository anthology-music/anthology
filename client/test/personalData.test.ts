import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const playlist = (id: string, name: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [name, id],
  name,
  owner_id: 'me',
  owner_name: 'Admin',
  visibility: 'private',
  folder_id: null,
  mine: true,
  generation: 'g1',
  entry_count: 2,
  duration_ms: 360_000,
  updated_at: '2026-10-29T10:00:00+00:00',
  ...overrides,
});

const track = (id: string, title: string) => ({
  id,
  key: [],
  title,
  artist: 'Nordlicht',
  album: 'Polarnacht',
  album_artist: 'Nordlicht',
  release_id: 'polarnacht',
  recording_id: `recording-${id}`,
  disc_number: 1,
  track_number: 1,
  duration_ms: 180_000,
  format: 'flac',
  sample_rate_hz: 44_100,
  bit_depth: 16,
  bitrate_kbps: null,
  effective_quality: null,
  quality_status: null,
  cover: null,
});

const entry = (id: string, title: string, by: string) => ({
  id,
  key: [id, id],
  position_key: id,
  track: track(`t-${id}`, title),
  added_by: by,
  added_by_name: by,
  added_at: '2026-10-29T10:00:00+00:00',
});

interface Call {
  method: string;
  path: string;
  body: unknown;
}

async function setup(path: string) {
  const calls: Call[] = [];
  const record =
    (answer: () => Response = () => new Response(null, { status: 204 })) =>
    async (request: Request) => {
      const text = request.method === 'GET' ? '' : await request.text();
      let body: unknown = text;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        // a file body
      }
      calls.push({ method: request.method, path: new URL(request.url).pathname, body });
      return answer();
    };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role: 'listener' })),
      'POST /api/v1/playlists': record(() => json({ id: 'new' }, 201)),
      'PATCH /api/v1/playlists/p1': record(),
      'POST /api/v1/playlists/p1/entries': record(() =>
        json({ entries: 1, edit_id: 'e-add', shortened: false }),
      ),
      'POST /api/v1/playlists/p1/entries/remove': record(() => json({ edit_id: 'e-remove' })),
      'POST /api/v1/playlists/p1/entries/move': record(() => json({ edit_id: 'e-move' })),
      'POST /api/v1/playlists/edits/e-remove/undo': record(),
      'POST /api/v1/playlist-folders': record(() => json({ id: 'f1' }, 201)),
      'POST /api/v1/playlists/import': record(() =>
        json({ id: 'imp', entries: 3, unmatched: ['Unbekannt - Nirgends'] }, 201),
      ),
      'PUT /api/v1/favorites/release/polarnacht': record(),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path, guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, calls };
}

async function serve(socket: FakeSocket, stream: string, rows: Record<string, unknown>[]) {
  const matching = () =>
    socket.sent.filter(
      (message): message is Subscribe =>
        message.type === 'subscribe' && message.data.stream === stream && message.data.end !== 0,
    );
  await vi.waitFor(() => expect(matching().length).toBeGreaterThan(0));
  for (const { sub } of matching()) {
    socket.receive({
      type: 'snapshot_meta',
      sub,
      seq: 1,
      data: { total: rows.length, counters: {} },
    });
    if (rows.length) socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  }
  await flushPromises();
}

const sent = (calls: Call[], method: string, path: string) =>
  calls.filter((call) => call.method === method && call.path === path).map((call) => call.body);

afterEach(() => {
  document.body.innerHTML = '';
});

describe('personal data', () => {
  it('lists own playlists by folder and the shared ones of others', async () => {
    const { wrapper, socket, calls } = await setup('/local/playlists');
    await serve(socket, 'personal.playlist_folders', [
      { id: 'f1', key: ['Konzerte', 'f1'], name: 'Konzerte' },
    ]);
    await serve(socket, 'personal.playlists', [
      playlist('p1', 'Abend', { folder_id: 'f1' }),
      playlist('p2', 'Morgen'),
      playlist('p3', 'Party', { mine: false, owner_name: 'lena', visibility: 'shared' }),
    ]);

    const text = wrapper.find('.library-section').text();
    expect(text.indexOf('Konzerte')).toBeLessThan(text.indexOf('Abend'));
    expect(text.indexOf('Meine Playlists')).toBeLessThan(text.indexOf('Morgen'));
    expect(text.indexOf('Von anderen geteilt')).toBeLessThan(text.indexOf('Party'));
    expect(wrapper.find('[data-testid="playlist-Party"]').text()).toContain('lena');

    await wrapper.find('[data-testid="playlist-new-name"]').setValue('Neu');
    await wrapper.find('[data-testid="playlist-create"]').trigger('submit');
    await vi.waitFor(() => expect(wrapper.router.currentRoute.value.name).toBe('playlist'));
    expect(sent(calls, 'POST', '/api/v1/playlists')).toEqual([
      { name: 'Neu', visibility: 'private' },
    ]);

    const file = new File(['#EXTM3U\n'], 'Urlaub.m3u8', { type: 'audio/x-mpegurl' });
    await wrapper.router.push('/local/playlists');
    await flushPromises();
    const input = wrapper.find('[data-testid="playlist-import"]');
    Object.defineProperty(input.element, 'files', { value: [file] });
    await input.trigger('change');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="playlist-imported"]').text()).toContain(
        '1 Eintrag nicht gefunden',
      ),
    );
  });

  it('shows who added entries, removes, undoes and moves them', async () => {
    const { wrapper, socket, calls } = await setup('/local/playlists/p1');
    await serve(socket, 'personal.playlist_folders', []);
    await serve(socket, 'personal.playlists', [
      playlist('p1', 'Party', { visibility: 'shared', mine: false, owner_name: 'lena' }),
    ]);
    await serve(socket, 'personal.playlist.entries', [
      entry('a', 'Eisfeld', 'lena'),
      entry('b', 'Treibeis', 'Admin'),
    ]);

    expect(wrapper.find('[data-testid="playlist-title"]').text()).toBe('Party');
    expect(wrapper.find('[data-testid="entry-a"]').text()).toContain('von lena');
    // Not the owner: no sharing, renaming or deleting.
    expect(wrapper.find('[data-testid="playlist-share"]').exists()).toBe(false);
    await wrapper.find('[data-testid="entry-remove-a"]').trigger('click');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="playlist-edit"]').text()).toContain('1 Titel entfernt'),
    );
    await wrapper.find('[data-testid="playlist-undo"]').trigger('click');
    await wrapper.find('[data-testid="entry-down-a"]').trigger('click');
    await wrapper.find('[data-testid="entry-up-b"]').trigger('click');

    await vi.waitFor(() => {
      expect(sent(calls, 'POST', '/api/v1/playlists/p1/entries/remove')).toEqual([{ ids: ['a'] }]);
      expect(sent(calls, 'POST', '/api/v1/playlists/edits/e-remove/undo')).toHaveLength(1);
      expect(sent(calls, 'POST', '/api/v1/playlists/p1/entries/move')).toEqual([
        { ids: ['a'], after: 'b' },
        { ids: ['b'], after: null },
      ]);
    });
  });

  it('lets the owner share a playlist', async () => {
    const { wrapper, socket, calls } = await setup('/local/playlists/p1');
    await serve(socket, 'personal.playlist_folders', []);
    await serve(socket, 'personal.playlists', [playlist('p1', 'Abend')]);

    await wrapper.find('[data-testid="playlist-share"]').trigger('click');

    await vi.waitFor(() =>
      expect(sent(calls, 'PATCH', '/api/v1/playlists/p1')).toEqual([{ visibility: 'shared' }]),
    );
  });

  it('marks an album as a favorite and adds it to a playlist', async () => {
    const { wrapper, socket, calls } = await setup('/local/releases/polarnacht');
    await serve(socket, 'library.release', [
      {
        id: 'polarnacht',
        key: ['polarnacht'],
        title: 'Polarnacht',
        album_artist: 'Nordlicht',
        album_artist_id: 'nordlicht',
        edition: null,
        year: 2024,
        disc_count: 1,
        track_count: 3,
        cover: null,
      },
    ]);
    await serve(socket, 'personal.favorites', []);

    const heart = wrapper.find('[data-testid="favorite-release-polarnacht"]');
    expect(heart.attributes('aria-pressed')).toBe('false');
    await heart.trigger('click');
    await vi.waitFor(() =>
      expect(
        wrapper.find('[data-testid="favorite-release-polarnacht"]').attributes('aria-pressed'),
      ).toBe('true'),
    );
    await wrapper.find('[data-testid="release-to-playlist"]').trigger('click');
    await serve(socket, 'personal.playlists', [playlist('p1', 'Abend')]);
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="add-to-Abend"]')).not.toBeNull(),
    );
    document.body.querySelector<HTMLElement>('[data-testid="add-to-Abend"]')!.click();

    await vi.waitFor(() =>
      expect(sent(calls, 'POST', '/api/v1/playlists/p1/entries')).toEqual([
        {
          ids: null,
          rule: { list: 'release_tracks', release_id: 'polarnacht' },
          at_start: false,
        },
      ]),
    );
    expect(sent(calls, 'PUT', '/api/v1/favorites/release/polarnacht')).toHaveLength(1);
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="playlist-message"]').text()).toContain('„Abend“'),
    );
  });
});
