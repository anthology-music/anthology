import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import { type AudioLike, setAudioFactory } from '@/features/playback/audio';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

class FakeAudio extends EventTarget implements AudioLike {
  src = '';
  currentTime = 0;
  duration = Number.NaN;
  paused = true;
  volume = 1;
  plays = 0;

  play(): Promise<void> {
    this.plays += 1;
    if (this.paused) {
      this.paused = false;
      this.dispatchEvent(new Event('play'));
    }
    return Promise.resolve();
  }

  pause(): void {
    if (!this.paused) {
      this.paused = true;
      this.dispatchEvent(new Event('pause'));
    }
  }

  canPlayType(type: string): string {
    if (type.includes('aiff')) return '';
    return type === 'audio/flac' ? 'maybe' : 'probably';
  }

  /** The browser loaded the file's metadata. */
  loaded(seconds = 240): void {
    this.duration = seconds;
    this.dispatchEvent(new Event('durationchange'));
    this.dispatchEvent(new Event('loadedmetadata'));
  }

  emit(type: string): void {
    this.dispatchEvent(new Event(type));
  }
}

const track = (id: string, format = 'flac') => ({
  id,
  key: [],
  title: `Titel ${id}`,
  artist: 'Nordlicht',
  album: 'Polarnacht',
  album_artist: 'Nordlicht',
  release_id: 'polarnacht',
  recording_id: `recording-${id}`,
  disc_number: 1,
  track_number: 1,
  duration_ms: 240_000,
  format,
  sample_rate_hz: 44_100,
  bit_depth: 16,
  bitrate_kbps: null,
  effective_quality: null,
  quality_status: null,
});

const state = (
  current: string | null,
  {
    next = null as string | null,
    position = 0,
    playing = false,
    format = 'flac',
    generation = 'g1',
  } = {},
) => ({
  id: 'queue-1',
  key: ['queue-1'],
  generation,
  current_entry_id: current,
  current: current ? track(`t-${current}`, format) : null,
  next_entry_id: next,
  position_ms: position,
  playing,
  entries: 3,
  shortened: false,
  updated_at: '2026-10-27T10:00:00+00:00',
});

async function setup(path = '/local/albums', expiresInMs = 3_600_000) {
  const audio = new FakeAudio();
  setAudioFactory(() => audio);
  const calls: { method: string; path: string; body: unknown }[] = [];
  const record = async (request: Request) => {
    const body: unknown =
      request.method === 'GET'
        ? null
        : await request.text().then((text) => (text ? JSON.parse(text) : null));
    calls.push({ method: request.method, path: new URL(request.url).pathname, body });
  };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role: 'listener' })),
      'POST /api/v1/playback/queue': async (request) => {
        await record(request);
        return json({ entries: 3, shortened: false });
      },
      'POST /api/v1/playback/urls': async (request) => {
        await record(request);
        const { entry_ids } = calls.at(-1)!.body as { entry_ids: string[] };
        return json(
          entry_ids.map((id) => ({
            entry_id: id,
            // Entry "failed": the server found no delivery (its transcode failed).
            url: id === 'failed' ? null : `/api/v1/media/originals/file-${id}?sig=x`,
            expires_at: new Date(Date.now() + expiresInMs).toISOString(),
            format: 'flac',
          })),
        );
      },
      'POST /api/v1/playback/skip': async (request) => {
        await record(request);
        return json({ current_entry_id: 'next' });
      },
      'DELETE /api/v1/playback/queue/entries/2': async (request) => {
        await record(request);
        return new Response(null, { status: 204 });
      },
      'PUT /api/v1/playback/state': async (request) => {
        await record(request);
        return new Response(null, { status: 204 });
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
  return { wrapper, socket, audio, calls };
}

function subscription(socket: FakeSocket, stream: string): Subscribe | undefined {
  return socket.sent
    .filter(
      (message): message is Subscribe =>
        message.type === 'subscribe' && message.data.stream === stream,
    )
    .at(-1);
}

async function serveState(socket: FakeSocket, row: ReturnType<typeof state>, seq = 1) {
  await vi.waitFor(() => expect(subscription(socket, 'playback.state')).toBeDefined());
  const { sub } = subscription(socket, 'playback.state')!;
  if (seq === 1) {
    socket.receive({ type: 'snapshot_meta', sub, seq, data: { total: 1, counters: {} } });
    socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows: [row] } });
  } else {
    socket.receive({
      type: 'delta',
      sub,
      seq,
      data: { op: 'upsert', id: row.id, key: row.key, row, total: 1 },
    });
  }
  await flushPromises();
}

const posted = (calls: { path: string; body: unknown }[], path: string) =>
  calls.filter((call) => call.path === path).map((call) => call.body);

afterEach(() => {
  setAudioFactory(() => new Audio());
});

describe('player', () => {
  it('resumes paused at the reported position after a reload', async () => {
    const { wrapper, socket, audio, calls } = await setup();
    await serveState(socket, state('1', { next: '2', position: 120_000, playing: true }));
    await vi.waitFor(() => expect(audio.src).toContain('file-1'));
    audio.loaded();

    expect(posted(calls, '/api/v1/playback/urls')).toEqual([{ entry_ids: ['1', '2'] }]);
    expect(audio.currentTime).toBe(120);
    expect(audio.plays).toBe(0); // no autoplay after a reload
    expect(wrapper.find('[data-testid="player-title"]').text()).toBe('Titel t-1');
    await wrapper.find('[data-testid="player-toggle"]').trigger('click');
    await vi.waitFor(() => expect(audio.plays).toBe(1));
    await vi.waitFor(() =>
      expect(posted(calls, '/api/v1/playback/state').at(-1)).toEqual({
        current_entry_id: '1',
        position_ms: 120_000,
        playing: true,
      }),
    );
  });

  it('plays an album and goes on to the next entry at the end of a track', async () => {
    const { wrapper, socket, audio, calls } = await setup();
    await serveState(socket, state(null));
    const { usePlayerStore } = await import('@/features/playback/store');
    await usePlayerStore().playList({ list: 'release_tracks', release_id: 'polarnacht' });
    await serveState(socket, state('1', { next: '2', playing: true }), 2);
    await vi.waitFor(() => expect(audio.plays).toBe(1));

    expect(posted(calls, '/api/v1/playback/queue')).toEqual([
      { mode: 'replace', rule: { list: 'release_tracks', release_id: 'polarnacht' }, start: null },
    ]);
    audio.emit('ended');
    await vi.waitFor(() =>
      expect(posted(calls, '/api/v1/playback/skip')).toEqual([{ by: 1, playing: true }]),
    );
    await serveState(socket, state('2', { playing: true }), 3);
    await vi.waitFor(() => expect(audio.src).toContain('file-2'));
    expect(audio.plays).toBe(2);
    expect(wrapper.find('[data-testid="player-title"]').text()).toBe('Titel t-2');
  });

  it('skips entries without a delivery and marks them', async () => {
    const { wrapper, socket, audio, calls } = await setup();
    await serveState(socket, state('1', { playing: true }));
    await vi.waitFor(() => expect(audio.src).toContain('file-1'));
    await wrapper.find('[data-testid="player-toggle"]').trigger('click');
    await serveState(socket, state('failed', { format: 'aiff', playing: true }), 2);

    await vi.waitFor(() =>
      expect(posted(calls, '/api/v1/playback/skip')).toEqual([{ by: 1, playing: true }]),
    );
    expect(wrapper.find('[data-testid="player-problem"]').text()).toContain(
      'Auf diesem Gerät nicht abspielbar',
    );
    expect(posted(calls, '/api/v1/playback/urls')).toEqual([
      { entry_ids: ['1'] },
      { entry_ids: ['failed'] },
    ]);
  });

  it('restarts the track or goes back with previous', async () => {
    const { wrapper, socket, audio, calls } = await setup();
    await serveState(socket, state('1'));
    await vi.waitFor(() => expect(audio.src).toContain('file-1'));
    audio.loaded();
    audio.currentTime = 42;

    await wrapper.find('[data-testid="player-previous"]').trigger('click');
    await vi.waitFor(() => expect(audio.currentTime).toBe(0));
    expect(posted(calls, '/api/v1/playback/skip')).toEqual([]);
    audio.currentTime = 2;
    await wrapper.find('[data-testid="player-previous"]').trigger('click');
    await vi.waitFor(() =>
      expect(posted(calls, '/api/v1/playback/skip')).toEqual([{ by: -1, playing: false }]),
    );
  });

  it('renews URLs that expire within five minutes', async () => {
    const { socket, audio, calls } = await setup('/local/albums', 60_000);
    await serveState(socket, state('1', { next: '2' }));
    await vi.waitFor(() => expect(audio.src).toContain('file-1'));
    await serveState(socket, state('2'), 2);
    await vi.waitFor(() => expect(audio.src).toContain('file-2'));

    expect(posted(calls, '/api/v1/playback/urls')).toEqual([
      { entry_ids: ['1', '2'] },
      { entry_ids: ['2'] },
    ]);
  });

  it('plays an album from the album page and a track list from a track', async () => {
    const { wrapper, socket, calls } = await setup('/local/releases/polarnacht');
    await serveState(socket, state(null));
    const release = subscription(socket, 'library.release')!;
    socket.receive({
      type: 'snapshot_meta',
      sub: release.sub,
      seq: 1,
      data: { total: 1, counters: {} },
    });
    socket.receive({
      type: 'chunk',
      sub: release.sub,
      data: {
        chunk: 0,
        start: 0,
        rows: [
          {
            id: 'polarnacht',
            key: ['polarnacht'],
            title: 'Polarnacht',
            album_artist: 'Nordlicht',
            album_artist_id: 'nordlicht',
            edition: null,
            year: 2024,
            disc_count: 1,
            track_count: 2,
          },
        ],
      },
    });
    const tracks = subscription(socket, 'library.release.tracks')!;
    socket.receive({
      type: 'snapshot_meta',
      sub: tracks.sub,
      seq: 1,
      data: { total: 2, counters: {} },
    });
    socket.receive({
      type: 'chunk',
      sub: tracks.sub,
      data: { chunk: 0, start: 0, rows: [track('a'), track('b')] },
    });
    await flushPromises();

    await wrapper.find('[data-testid="play-release"]').trigger('click');
    await wrapper.find('[data-testid="play-b"]').trigger('click');
    await vi.waitFor(() => expect(posted(calls, '/api/v1/playback/queue')).toHaveLength(2));

    expect(posted(calls, '/api/v1/playback/queue')).toEqual([
      { mode: 'replace', rule: { list: 'release_tracks', release_id: 'polarnacht' }, start: null },
      { mode: 'replace', rule: { list: 'release_tracks', release_id: 'polarnacht' }, start: 'b' },
    ]);
  });

  it('shows the queue and removes an entry', async () => {
    const { wrapper, socket, calls } = await setup();
    await serveState(socket, state('1'));
    await wrapper.find('[data-testid="player-queue"]').trigger('click');
    const queue = await vi.waitFor(() => {
      const found = subscription(socket, 'playback.queue');
      expect(found).toBeDefined();
      return found!;
    });

    expect(queue.data.params).toEqual({ generation: 'g1' });
    socket.receive({
      type: 'snapshot_meta',
      sub: queue.sub,
      seq: 1,
      data: { total: 2, counters: {} },
    });
    socket.receive({
      type: 'chunk',
      sub: queue.sub,
      data: {
        chunk: 0,
        start: 0,
        rows: [
          { id: '1', key: [1024, 1], position: 1024, track: track('t-1') },
          { id: '2', key: [2048, 2], position: 2048, track: track('t-2') },
        ],
      },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="queue-panel"]').text()).toContain('Titel t-2');
    expect(wrapper.find('[data-testid="queue-entry-1"]').classes()).toContain(
      'queue-panel__row--current',
    );
    await wrapper.find('[data-testid="queue-remove-2"]').trigger('click');
    await vi.waitFor(() =>
      expect(calls.map((call) => `${call.method} ${call.path}`)).toContain(
        'DELETE /api/v1/playback/queue/entries/2',
      ),
    );
  });

  it('reports the playable formats for the hello', async () => {
    const { playableFormats } = await import('@/features/playback/formats');

    expect(playableFormats(new FakeAudio())).toEqual([
      'aac',
      'alac',
      'flac',
      'mp3',
      'opus',
      'vorbis',
      'wav',
    ]);
  });
});
