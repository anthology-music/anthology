import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const track = (id: string) => ({
  id,
  key: [1, `nordlicht\u0001${id}`, id],
  title: `Polka ${id}`,
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
});

/** A minimal server-side parser for the tokens used in these tests. */
function parsed(q: string) {
  const result = [];
  for (const match of q.matchAll(/(\w+):("[^"]*"|\S*)|(\S+)/g)) {
    const start = match.index;
    const end = start + match[0].length;
    if (match[1]) {
      const field = match[1];
      const known = ['genre', 'year', 'artist'].includes(field);
      result.push({
        text: match[0],
        kind: 'filter',
        start,
        end,
        field,
        op: '=',
        value: match[2]!.replaceAll('"', ''),
        error: known ? null : 'unknown_field',
      });
    } else {
      result.push({ text: match[0], kind: 'word', start, end, value: match[0] });
    }
  }
  return {
    tokens: result,
    types: q.includes('genre:') ? ['track'] : ['artist', 'release', 'track'],
  };
}

async function searchPage(path: string, role = 'editor') {
  const parses: string[] = [];
  const values: unknown[] = [];
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'GET /api/v1/search/parse': (request) => {
        const q = new URL(request.url).searchParams.get('q') ?? '';
        parses.push(q);
        return json(parsed(q));
      },
      'POST /api/v1/tagging/values': async (request) => {
        values.push(await request.json());
        return json({ items: 2, fields: { recording: {}, release: {}, track: {} } });
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
  return { wrapper, socket, parses, values };
}

function searches(socket: FakeSocket, stream?: string): Subscribe[] {
  return socket.sent.filter(
    (message): message is Subscribe =>
      message.type === 'subscribe' &&
      message.data.stream.startsWith('search.') &&
      (stream === undefined || message.data.stream === stream),
  );
}

async function serve(
  socket: FakeSocket,
  stream: string,
  rows: Record<string, unknown>[],
  total = rows.length,
  capped = 0,
) {
  await vi.waitFor(() => expect(searches(socket, stream).length).toBeGreaterThan(0));
  const { sub } = searches(socket, stream).at(-1)!;
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total, counters: { capped } } });
  socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  await flushPromises();
}

describe('search', () => {
  it('searches while typing and shows the counts per type first', async () => {
    const { wrapper, socket } = await searchPage('/local/albums');

    await wrapper.find('[data-testid="search-input"]').setValue('polka');
    await vi.waitFor(() => expect(wrapper.router.currentRoute.value.name).toBe('search'));
    await vi.waitFor(() => expect(searches(socket)).toHaveLength(3));
    expect(searches(socket).map((message) => message.data.params)).toEqual([
      { q: 'polka' },
      { q: 'polka' },
      { q: 'polka' },
    ]);
    await serve(socket, 'search.artists', []);
    await serve(socket, 'search.releases', [], 2503);
    await serve(socket, 'search.tracks', [track('a'), track('b')], 10_000, 1);

    expect(wrapper.find('[data-testid="search-count-track"]').text()).toBe('10.000+');
    expect(wrapper.find('[data-testid="search-count-release"]').text()).toBe('2.503');
    expect(wrapper.find('[data-testid="search-group-track"]').text()).toContain('Polka a');
    expect(wrapper.find('[data-testid="search-group-artist"]').text()).toContain('Keine Treffer');
    expect(wrapper.find('[data-testid="search-all-track"]').exists()).toBe(true);
  });

  it('shows filter chips and hints from the parsed text', async () => {
    const { wrapper, parses } = await searchPage(
      `/local/search?q=${encodeURIComponent('genre:Blasmusik colour:red Mozart')}`,
    );
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="search-chip-genre"]').exists()).toBe(true),
    );

    expect(parses).toEqual(['genre:Blasmusik colour:red Mozart']);
    expect(wrapper.find('[data-testid="search-chip-genre"]').text()).toContain('Genre: Blasmusik');
    expect(wrapper.find('[data-testid="search-hints"]').text()).toContain(
      'Unbekanntes Feld „colour“',
    );
    // genre: applies to tracks only.
    expect(wrapper.find('[data-testid="search-group-artist"]').exists()).toBe(false);
    await wrapper.find('[data-testid="search-chip-genre"] .q-chip__icon--remove').trigger('click');
    await vi.waitFor(() =>
      expect(wrapper.router.currentRoute.value.query.q).toBe('colour:red Mozart'),
    );
    expect((wrapper.find('[data-testid="search-input"]').element as HTMLInputElement).value).toBe(
      'colour:red Mozart',
    );
  });

  it('adds a chip as the same token the syntax produces', async () => {
    const { wrapper, socket } = await searchPage('/local/search?q=Mozart');

    await wrapper.find('[data-testid="search-add-filter"]').trigger('click');
    await wrapper.find('[data-testid="search-filter-value"]').setValue('Wiener Blasmusik');
    await wrapper.find('.search-page__add').trigger('submit');
    await vi.waitFor(() =>
      expect(wrapper.router.currentRoute.value.query.q).toBe('Mozart genre:"Wiener Blasmusik"'),
    );
    await vi.waitFor(() =>
      expect(searches(socket, 'search.tracks').at(-1)?.data.params).toEqual({
        q: 'Mozart genre:"Wiener Blasmusik"',
      }),
    );
  });

  it('searches within an album and removes the context', async () => {
    const { wrapper, socket } = await searchPage(
      '/local/search?q=eis&release_id=polarnacht&in=Polarnacht',
    );
    await vi.waitFor(() => expect(searches(socket)).toHaveLength(1));

    expect(searches(socket)[0]!.data).toMatchObject({
      stream: 'search.tracks',
      params: { q: 'eis', release_id: 'polarnacht' },
    });
    expect(wrapper.find('[data-testid="search-context"]').text()).toContain('In: Polarnacht');
    await wrapper.find('[data-testid="search-context"] .q-chip__icon--remove').trigger('click');
    await vi.waitFor(() => expect(wrapper.router.currentRoute.value.query).toEqual({ q: 'eis' }));
  });

  it('edits all track results with the search as rule', async () => {
    const { wrapper, socket, values } = await searchPage(
      '/local/search?q=polka&type=track&release_id=polarnacht&in=Polarnacht',
    );
    await serve(socket, 'search.tracks', [track('a'), track('b')]);

    expect(wrapper.find('[data-testid="search-list-count"]').text()).toBe('2');
    await wrapper.find('[data-testid="search-edit-all"]').trigger('click');
    await vi.waitFor(() => expect(values).toHaveLength(1));

    expect(values[0]).toEqual({
      rule: { list: 'search', q: 'polka', release_id: 'polarnacht', artist_id: null },
    });
  });

  it('offers editing to editors only', async () => {
    const { wrapper, socket } = await searchPage('/local/search?q=polka&type=track', 'listener');
    await serve(socket, 'search.tracks', [track('a')]);

    expect(wrapper.find('[data-testid="search-list-count"]').text()).toBe('1');
    expect(wrapper.find('[data-testid="search-edit-all"]').exists()).toBe(false);
  });
});
