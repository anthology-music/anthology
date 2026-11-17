import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import { parseDuration } from '@/features/works/duration';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const work = (id: string, title: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [title.toLowerCase(), id],
  title,
  type: 'original',
  composers: ['Ola Nord'],
  arrangers: [],
  instrumentation: null,
  grade: null,
  duration_sec: null,
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

const medley = {
  ...work('m1', 'Nordlicht-Medley', {
    type: 'medley',
    composers: [],
    arrangers: ['Jacob de Haan'],
    grade: '3',
    instrumentation: 'Harmoniemusik',
    duration_sec: 510,
  }),
  key: ['m1'],
  credits: [{ person_id: 'p1', name: 'Jacob de Haan', role: 'arranger' }],
  iswc: null,
  mb_work_id: null,
  recording_count: 0,
  content_count: 2,
  container_count: 0,
};

interface Call {
  method: string;
  path: string;
  body: unknown;
}

async function setup(path: string, role = 'editor', answers: Record<string, () => Response> = {}) {
  const calls: Call[] = [];
  const record =
    (answer: () => Response = () => new Response(null, { status: 204 })) =>
    async (request: Request) => {
      const text = request.method === 'GET' ? '' : await request.text();
      calls.push({
        method: request.method,
        path: new URL(request.url).pathname,
        body: text ? JSON.parse(text) : null,
      });
      return answer();
    };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'POST /api/v1/works': record(() => json({ id: 'new' }, 201)),
      'PUT /api/v1/works/m1/relations/order': record(),
      'POST /api/v1/works/m1/relations': record(
        answers['relation'] ?? (() => json({ id: 'r9' }, 201)),
      ),
      'PUT /api/v1/favorites/work/m1': record(),
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

function subscriptions(socket: FakeSocket, stream: string): Subscribe[] {
  return socket.sent.filter(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === stream && message.data.end !== 0,
  );
}

async function serve(
  socket: FakeSocket,
  stream: string,
  rows: Record<string, unknown>[],
  counters: Record<string, number> = {},
) {
  await vi.waitFor(() => expect(subscriptions(socket, stream).length).toBeGreaterThan(0));
  for (const { sub } of subscriptions(socket, stream)) {
    socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: rows.length, counters } });
    if (rows.length) socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  }
  await flushPromises();
}

const sent = (calls: Call[], method: string, path: string) =>
  calls.filter((call) => call.method === method && call.path === path).map((call) => call.body);

afterEach(() => {
  document.body.innerHTML = '';
});

describe('works', () => {
  it('lists works with the counts per type and filters by type', async () => {
    const { wrapper, socket } = await setup('/works');
    await serve(socket, 'works.list', [work('w1', 'Eisfeld'), medley], {
      all: 2,
      original: 1,
      medley: 1,
      arrangement: 0,
      adaptation: 0,
    });
    expect(wrapper.find('[data-testid="works-type-all"]').text()).toContain('2');
    expect(wrapper.find('[data-testid="works-type-medley"]').text()).toContain('1');
    expect(wrapper.text()).toContain('Nordlicht-Medley');
    expect(wrapper.text()).toContain('arr. Jacob de Haan');

    await wrapper.find('[data-testid="works-type-medley"]').trigger('click');
    await vi.waitFor(() =>
      expect(subscriptions(socket, 'works.list').at(-1)?.data.params).toEqual({ type: 'medley' }),
    );
  });

  it('creates a work with a new person as arranger', async () => {
    const { wrapper, socket, calls } = await setup('/works');
    await serve(socket, 'works.list', []);
    await wrapper.find('[data-testid="work-create"]').trigger('click');
    await flushPromises();
    const editor = document.querySelector('[data-testid="work-editor"]')!;
    const input = (selector: string) =>
      editor.querySelector<HTMLInputElement>(`[data-testid="${selector}"] input`) ??
      editor.querySelector<HTMLInputElement>(`input[data-testid="${selector}"]`)!;
    const title = input('work-title');
    title.value = 'Eisfeld (Harmoniemusik)';
    title.dispatchEvent(new Event('input'));
    const duration = input('work-duration');
    duration.value = '8:30';
    duration.dispatchEvent(new Event('input'));
    await flushPromises();
    editor.querySelector('form')!.dispatchEvent(new Event('submit'));
    await vi.waitFor(() => expect(sent(calls, 'POST', '/api/v1/works')).toHaveLength(1));
    expect(sent(calls, 'POST', '/api/v1/works')[0]).toMatchObject({
      title: 'Eisfeld (Harmoniemusik)',
      type: 'original',
      duration_sec: 510,
      credits: [],
    });
    await vi.waitFor(() => expect(wrapper.router.currentRoute.value.path).toBe('/works/new'));
  });

  it('shows a medley with playable and missing originals and reorders them', async () => {
    const { wrapper, socket, calls } = await setup('/works/m1');
    await serve(socket, 'works.work', [medley]);
    await serve(socket, 'works.work.contents', [
      {
        id: 'r1',
        key: [0, 'r1'],
        relation_type: 'medley_contains',
        position: 0,
        work: work('w1', 'Eisfeld'),
        track: track('t1', 'Eisfeld'),
        acquire_query: 'Nordlicht Eisfeld',
      },
      {
        id: 'r2',
        key: [1, 'r2'],
        relation_type: 'medley_contains',
        position: 1,
        work: work('w2', 'Sternbild'),
        track: null,
        acquire_query: 'Ola Nord Sternbild',
      },
    ]);
    await serve(socket, 'works.work.recordings', []);
    await serve(socket, 'works.work.containers', []);

    expect(wrapper.find('[data-testid="work-title-heading"]').text()).toBe('Nordlicht-Medley');
    expect(wrapper.find('[data-testid="work-kind"]').text()).toContain('Grad 3');
    expect(wrapper.find('[data-testid="work-kind"]').text()).toContain('8:30');
    expect(wrapper.find('[data-testid="work-contents"]').text()).toContain(
      '2 Titel · 1 in der Bibliothek',
    );
    expect(wrapper.find('[data-testid="original-play-Eisfeld"]').exists()).toBe(true);
    const acquire = wrapper.find('[data-testid="original-acquire-Sternbild"]');
    expect(acquire.attributes('href')).toContain('source_q=Ola+Nord+Sternbild');

    // The second original moves up.
    await wrapper.find('[aria-label="Sternbild nach oben"]').trigger('click');
    await vi.waitFor(() =>
      expect(sent(calls, 'PUT', '/api/v1/works/m1/relations/order')).toEqual([
        { relation_ids: ['r2', 'r1'] },
      ]),
    );

    await wrapper.find('[data-testid="favorite-work-m1"]').trigger('click');
    await vi.waitFor(() => expect(sent(calls, 'PUT', '/api/v1/favorites/work/m1')).toHaveLength(1));
  });

  it('reports a refused cycle', async () => {
    const { wrapper, socket } = await setup('/works/m1', 'editor', {
      relation: () => json({ detail: 'cycle' }, 409),
    });
    await serve(socket, 'works.work', [medley]);
    await serve(socket, 'works.work.contents', []);
    await wrapper.find('[data-testid="original-add"]').trigger('click');
    await flushPromises();
    const query = document.querySelector<HTMLInputElement>(
      '[data-testid="pick-work-query"] input, input[data-testid="pick-work-query"]',
    )!;
    query.value = 'Grosses';
    query.dispatchEvent(new Event('input'));
    await serve(socket, 'search.works', [work('g1', 'Grosses Medley', { type: 'medley' })]);
    (document.querySelector('[data-testid="pick-work-Grosses Medley"]') as HTMLElement).click();
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="work-problem"]').text()).toContain('selbst enthalten'),
    );
  });

  it('hides editing from listeners', async () => {
    const { wrapper, socket } = await setup('/works/m1', 'listener');
    await serve(socket, 'works.work', [medley]);
    await serve(socket, 'works.work.contents', []);
    expect(wrapper.find('[data-testid="work-edit"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="original-add"]').exists()).toBe(false);
  });

  it('offers the works of a track in its menu', async () => {
    const { wrapper, socket } = await setup('/local/releases/polarnacht', 'listener');
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
        track_count: 1,
        cover: null,
      },
    ]);
    await serve(socket, 'library.release.tracks', [
      { ...track('t1', 'Eisfeld'), key: [1, 1, 't1'] },
    ]);
    await wrapper.find('[data-testid="more-t1"]').trigger('click');
    await serve(socket, 'works.recording', [
      { id: 'l1', key: ['nordlicht-medley', 'l1'], origin: 'musicbrainz', work: medley },
    ]);
    await vi.waitFor(() =>
      expect(document.querySelector('[data-testid="track-work-Nordlicht-Medley"]')).not.toBeNull(),
    );
    expect(subscriptions(socket, 'works.recording')[0]!.data.params).toEqual({
      recording_id: 'recording-t1',
    });
  });

  it('parses durations', () => {
    expect(parseDuration('8:30')).toBe(510);
    expect(parseDuration('1:02:03')).toBe(3723);
    expect(parseDuration('7')).toBe(420);
    expect(parseDuration('')).toBeNull();
    expect(parseDuration('8:75')).toBeUndefined();
    expect(parseDuration('acht')).toBeUndefined();
  });
});
