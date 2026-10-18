import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import { geometry, scrollTopFor } from '@/components/virtualGeometry';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const COUNTERS = { artists: 21_417, releases: 38_905, tracks: 512_340, recordings: 510_000 };

const artist = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [id],
  name: `Artist ${id}`,
  release_count: 2,
  track_count: 14,
  ...overrides,
});

const release = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [id],
  title: `Album ${id}`,
  album_artist: 'Nordlicht',
  album_artist_id: 'nordlicht',
  edition: null,
  year: 2024,
  disc_count: 1,
  track_count: 3,
  ...overrides,
});

const track = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [1, 1, id],
  title: `Track ${id}`,
  artist: 'Nordlicht',
  album: 'Polarnacht',
  album_artist: 'Nordlicht',
  release_id: 'polarnacht',
  recording_id: `recording-${id}`,
  disc_number: 1,
  track_number: 1,
  duration_ms: 252_000,
  format: 'flac',
  sample_rate_hz: 96_000,
  bit_depth: 24,
  bitrate_kbps: null,
  ...overrides,
});

async function libraryPage(path: string) {
  const services = fakeServices(
    { 'POST /api/v1/auth/refresh': () => json(tokens()) },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path, guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await vi.waitFor(() => expect(subscriptions(socket).length).toBeGreaterThan(1));
  return { wrapper, socket };
}

function subscriptions(socket: FakeSocket, stream?: string): Subscribe[] {
  return socket.sent.filter(
    (message): message is Subscribe =>
      message.type === 'subscribe' && (stream === undefined || message.data.stream === stream),
  );
}

/** The latest subscription to `stream`; lists only, unless `counts` (the empty window). */
async function subscribed(socket: FakeSocket, stream: string, counts = false): Promise<Subscribe> {
  const matching = () =>
    subscriptions(socket, stream).filter((message) => (message.data.end === 0) === counts);
  await vi.waitFor(() => expect(matching().length).toBeGreaterThan(0));
  return matching().at(-1)!;
}

/** Answer the latest subscription to `stream` with its total and rows. */
async function serve(
  socket: FakeSocket,
  stream: string,
  rows: object[],
  { total = rows.length, counters = {}, start = 0, counts = false } = {},
) {
  const { sub } = await subscribed(socket, stream, counts);
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total, counters } });
  if (rows.length) {
    socket.receive({
      type: 'chunk',
      sub,
      data: { chunk: 0, start, rows: rows as Record<string, unknown>[] },
    });
  }
  await flushPromises();
  return sub;
}

describe('library views', () => {
  it('redirects the Local view to the albums', async () => {
    const { wrapper } = await libraryPage('/local');

    expect(wrapper.router.currentRoute.value.name).toBe('library-albums');
    expect(wrapper.find('h1').text()).toBe('Alben');
  });

  it('shows the live counts of the sections without loading rows', async () => {
    const { wrapper, socket } = await libraryPage('/local/albums');
    const [nav] = subscriptions(socket, 'library.artists');
    expect(nav!.data).toMatchObject({ start: 0, end: 0 });

    await serve(socket, 'library.artists', [], { total: 21_417, counters: COUNTERS, counts: true });
    const count = (section: string) =>
      wrapper.find(`[data-testid="library-nav-${section}"] .library-nav__count`).text();
    expect(count('releases')).toBe('38.905');
    expect(count('artists')).toBe('21.417');
    expect(count('tracks')).toBe('512.340');

    socket.receive({
      type: 'delta',
      sub: nav!.sub,
      seq: 2,
      data: {
        op: 'upsert',
        id: 'x',
        key: ['x'],
        row: artist('x'),
        total: 21_418,
        counters: { ...COUNTERS, artists: 21_418, releases: 38_906 },
      },
    });
    await flushPromises();
    expect(count('releases')).toBe('38.906');
  });

  it.each([
    ['/local/albums', 'Alben', 'library.releases'],
    ['/local/artists', 'Künstler', 'library.artists'],
    ['/local/tracks', 'Titel', 'library.tracks'],
  ])('renders the section %s from its stream', async (path, title, stream) => {
    const { wrapper, socket } = await libraryPage(path);

    expect(wrapper.find('h1').text()).toBe(title);
    const list = subscriptions(socket, stream).find((message) => message.data.end! > 0);
    expect(list?.data).toMatchObject({ params: {}, start: 0, end: 100 });
  });

  it('shows album and artist rows as links', async () => {
    const { wrapper, socket } = await libraryPage('/local/albums');
    await serve(socket, 'library.releases', [release('polarnacht', { edition: 'Deluxe' })]);

    const row = wrapper.find('[data-testid="release-polarnacht"]');
    expect(row.text()).toContain('Album polarnacht');
    expect(row.text()).toContain('Nordlicht · Deluxe');
    expect(row.attributes('href')).toBe('/local/releases/polarnacht');

    await wrapper.router.push('/local/artists');
    await serve(socket, 'library.artists', [artist('nordlicht', { name: 'Nordlicht' })], {
      counters: COUNTERS,
    });
    const artistRow = wrapper.find('[data-testid="artist-nordlicht"]');
    expect(artistRow.text()).toContain('2 Alben · 14 Titel');
    expect(artistRow.attributes('href')).toBe('/local/artists/nordlicht');
  });

  it('links a row of the track section to its album', async () => {
    const { wrapper, socket } = await libraryPage('/local/tracks');
    await serve(socket, 'library.tracks', [track('a', { format: 'mp3', bitrate_kbps: 320 })]);

    const row = wrapper.find('[data-testid="track-a"]');
    expect(row.attributes('href')).toBe('/local/releases/polarnacht');
    expect(row.text()).toContain('Nordlicht · Polarnacht');
    expect(row.text()).toContain('MP3 320');
    expect(row.text()).toContain('4:12');
  });

  it('shows the artist page with its header and releases', async () => {
    const { wrapper, socket } = await libraryPage('/local/artists/nordlicht');
    const header = await subscribed(socket, 'library.artist');
    const list = await subscribed(socket, 'library.artist.releases');
    expect(header.data.params).toEqual({ artist_id: 'nordlicht' });
    expect(list.data.params).toEqual({ artist_id: 'nordlicht' });

    await serve(socket, 'library.artist', [artist('nordlicht', { name: 'Nordlicht' })]);
    await serve(socket, 'library.artist.releases', [release('polarnacht')]);

    expect(wrapper.find('[data-testid="artist-name"]').text()).toBe('Nordlicht');
    expect(wrapper.find('[data-testid="artist-counts"]').text()).toBe('2 Alben · 14 Titel');
    expect(wrapper.find('.breadcrumb').text()).toContain('Bibliothek');
    expect(wrapper.find('[data-testid="release-polarnacht"]').exists()).toBe(true);
  });

  it('shows the album page with header, disc numbers, guest credits and format labels', async () => {
    const { wrapper, socket } = await libraryPage('/local/releases/polarnacht');
    await serve(socket, 'library.release', [
      release('polarnacht', { title: 'Polarnacht', disc_count: 2, track_count: 14 }),
    ]);
    await serve(socket, 'library.release.tracks', [
      track('a', { title: 'Eisfeld' }),
      track('b', { title: 'Polarnacht', artist: 'Nordlicht feat. Glas', disc_number: 2 }),
    ]);

    expect(wrapper.find('[data-testid="release-title"]').text()).toBe('Polarnacht');
    expect(wrapper.find('[data-testid="release-meta"]').text()).toContain('14 Titel · 2 CDs');
    expect(wrapper.find('[data-testid="release-artist"]').attributes('href')).toBe(
      '/local/artists/nordlicht',
    );
    expect(wrapper.find('.breadcrumb').text()).toMatch(/Bibliothek.*Nordlicht.*Polarnacht/);

    const own = wrapper.find('[data-testid="track-a"]');
    const guest = wrapper.find('[data-testid="track-b"]');
    expect(own.text()).toContain('1-01');
    expect(own.find('[data-testid="track-artist"]').exists()).toBe(false);
    expect(guest.text()).toContain('2-01');
    expect(guest.find('[data-testid="track-artist"]').text()).toBe('Nordlicht feat. Glas');
    expect(own.text()).toContain('FLAC 24/96');
    // The format is technical information, not a quality badge (effective quality unknown).
    expect(own.find('.badge').exists()).toBe(false);
  });

  it('says when an album does not exist', async () => {
    const { wrapper, socket } = await libraryPage('/local/releases/unknown');
    await serve(socket, 'library.release', []);

    expect(wrapper.find('[data-testid="library-missing"]').text()).toContain(
      'Dieses Album gibt es nicht.',
    );
    expect(wrapper.find('[data-testid="library-missing"] a').attributes('href')).toBe(
      '/local/albums',
    );
  });

  it('says when the open album is removed', async () => {
    const { wrapper, socket } = await libraryPage('/local/releases/polarnacht');
    const sub = await serve(socket, 'library.release', [release('polarnacht')]);
    expect(wrapper.find('[data-testid="library-missing"]').exists()).toBe(false);

    socket.receive({
      type: 'delta',
      sub,
      seq: 2,
      data: { op: 'remove', id: 'polarnacht', key: null, row: null, total: 0 },
    });
    await flushPromises();

    expect(wrapper.find('[data-testid="library-missing"]').text()).toContain(
      'Dieses Album gibt es nicht mehr.',
    );
  });

  it('restores the scroll position when going back to a section', async () => {
    const { wrapper, socket } = await libraryPage('/local/albums');
    await serve(socket, 'library.releases', [release('first')], { total: 38_905 });

    const list = wrapper.find('.vlist');
    (list.element as HTMLElement).scrollTop = scrollTopFor(20_000, 52, geometry(38_905, 52, 600));
    await list.trigger('scroll');
    await wrapper.router.push('/local/releases/first');
    await subscribed(socket, 'library.release');
    const before = subscriptions(socket, 'library.releases').length;
    wrapper.router.back();

    await vi.waitFor(() =>
      expect(subscriptions(socket, 'library.releases').length).toBeGreaterThan(before),
    );
    const again = subscriptions(socket, 'library.releases').at(-1)!;
    expect(again.data.start).toBe(19_950);
    await serve(socket, 'library.releases', [release('far')], { total: 38_905, start: 20_000 });
    await vi.waitFor(() => expect(wrapper.find('[aria-posinset="20001"]').exists()).toBe(true));
  });
});
