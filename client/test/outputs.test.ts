import type { ClientMessage } from '@anthology/api-types';
import { flushPromises, type VueWrapper } from '@vue/test-utils';
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
    this.paused = false;
    this.dispatchEvent(new Event('play'));
    return Promise.resolve();
  }

  pause(): void {
    if (!this.paused) {
      this.paused = true;
      this.dispatchEvent(new Event('pause'));
    }
  }

  canPlayType(): string {
    return 'probably';
  }

  emit(type: string): void {
    this.dispatchEvent(new Event(type));
  }
}

const track = {
  id: 't1',
  key: [],
  title: 'Schneesturm',
  artist: 'Nordlicht',
  album: 'Polarnacht',
  album_artist: 'Nordlicht',
  release_id: 'polarnacht',
  recording_id: 'r1',
  disc_number: 1,
  track_number: 5,
  duration_ms: 240_000,
  format: 'flac',
  sample_rate_hz: 44_100,
  bit_depth: 16,
  bitrate_kbps: null,
  effective_quality: null,
  quality_status: null,
};

const state = (zone: string | null, { playing = true, position = 80_000 } = {}) => ({
  id: 'user-device-1',
  key: ['queue'],
  output_zone_id: zone,
  generation: 'g1',
  current_entry_id: '5',
  current: track,
  next_entry_id: '6',
  position_ms: position,
  playing,
  entries: 6,
  shortened: false,
  updated_at: '2026-10-28T10:00:00+00:00',
});

const system = {
  id: 's1',
  key: ['192.168.1.20:47365', 0, 'Raumfeld', '192.168.1.20:47365'],
  kind: 'system',
  name: 'Raumfeld (192.168.1.20:47365)',
  system_id: 's1',
  zone_id: null,
  adapter: 'raumfeld',
  address: '192.168.1.20:47365',
  origin: 'manual',
  state: 'online',
  reason: null,
};
const zone = (id: string, name: string, online = true) => ({
  id,
  key: [system.address, 1, name, id],
  kind: 'zone',
  name,
  system_id: 's1',
  zone_id: id,
  online,
  volume: 30,
  muted: false,
  formats: ['flac', 'mp3'],
});
const room = (id: string, name: string, zoneId: string | null) => ({
  id,
  key: [system.address, 2, name, id],
  kind: 'room',
  name,
  system_id: 's1',
  zone_id: zoneId,
  online: true,
  volume: 25,
  muted: false,
});
const OUTPUTS = [
  system,
  zone('z1', 'Wohnzimmer'),
  zone('z2', 'Garten', false),
  room('r1', 'Wohnzimmer', 'z1'),
  room('r2', 'Küche', null),
];

interface Call {
  method: string;
  path: string;
  body: unknown;
}

async function setup(path = '/local/albums', role = 'listener') {
  const audio = new FakeAudio();
  setAudioFactory(() => audio);
  const calls: Call[] = [];
  const recorded =
    (status = 204, answer: unknown = null) =>
    async (request: Request) => {
      const text = request.method === 'GET' ? '' : await request.text();
      calls.push({
        method: request.method,
        path: new URL(request.url).pathname,
        body: text ? JSON.parse(text) : null,
      });
      return answer === null ? new Response(null, { status }) : json(answer, status);
    };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'PUT /api/v1/playback/output': recorded(),
      'PUT /api/v1/playback/state': recorded(),
      'POST /api/v1/playback/skip': recorded(200, { current_entry_id: '6' }),
      'POST /api/v1/playback/urls': recorded(200, [
        {
          entry_id: '5',
          url: '/api/v1/media/originals/a5?sig=x',
          expires_at: new Date(Date.now() + 3_600_000).toISOString(),
          format: 'flac',
        },
      ]),
      'PUT /api/v1/playback/zones/z1/volume': recorded(),
      'PUT /api/v1/playback/rooms/r1/volume': recorded(),
      'PUT /api/v1/playback/rooms/r2/zone': recorded(),
      'DELETE /api/v1/playback/rooms/r1/zone': recorded(),
      'POST /api/v1/playback/systems': async (request) => {
        const body = (await request.json()) as { address: string };
        calls.push({ method: 'POST', path: '/api/v1/playback/systems', body });
        return body.address.includes('/')
          ? json({ detail: 'invalid_address' }, 422)
          : json({ id: 's2' }, 201);
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

async function serve(socket: FakeSocket, stream: string, rows: Record<string, unknown>[]) {
  // Every subscription of the stream (the player bar and a settings section may both have one).
  await vi.waitFor(() => expect(subscription(socket, stream)).toBeDefined());
  const subs = socket.sent
    .filter(
      (message): message is Subscribe =>
        message.type === 'subscribe' && message.data.stream === stream,
    )
    .map((message) => message.sub);
  for (const sub of new Set(subs)) {
    socket.receive({
      type: 'snapshot_meta',
      sub,
      seq: 1,
      data: { total: rows.length, counters: {} },
    });
    socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  }
  await flushPromises();
}

async function update(socket: FakeSocket, stream: string, row: { id: string; key: unknown[] }) {
  const { sub } = subscription(socket, stream)!;
  socket.receive({
    type: 'delta',
    sub,
    seq: 2,
    data: { op: 'upsert', id: row.id, key: row.key, row, total: 1 },
  });
  await flushPromises();
}

const sent = (calls: Call[], method: string, path: string) =>
  calls.filter((call) => call.method === method && call.path === path).map((call) => call.body);

function menuItem(testid: string): HTMLElement | null {
  return document.body.querySelector<HTMLElement>(`[data-testid="${testid}"]`);
}

async function openPicker(wrapper: VueWrapper) {
  await wrapper.find('[data-testid="output-picker"]').trigger('click');
  await vi.waitFor(() => expect(menuItem('output-device')).not.toBeNull());
}

afterEach(() => {
  setAudioFactory(() => new Audio());
  document.body.innerHTML = '';
});

describe('outputs', () => {
  it('lists this device and the zones and hands the queue to a zone', async () => {
    const { wrapper, socket, calls } = await setup();
    await serve(socket, 'playback.state', [state(null, { playing: false })]);
    await serve(socket, 'playback.outputs', OUTPUTS);

    await openPicker(wrapper);
    const garden = menuItem('output-zone-Garten')!;
    expect(menuItem('output-device')!.getAttribute('aria-selected')).toBe('true');
    expect(menuItem('output-zone-Wohnzimmer')!.textContent).toContain('Raumfeld');
    expect(garden.textContent).toContain('Nicht erreichbar');
    expect(garden.getAttribute('aria-disabled')).toBe('true');
    menuItem('output-zone-Wohnzimmer')!.click();

    await vi.waitFor(() =>
      expect(sent(calls, 'PUT', '/api/v1/playback/output')).toEqual([{ zone_id: 'z1' }]),
    );
  });

  it('is a remote control while a zone plays', async () => {
    const { wrapper, socket, audio, calls } = await setup();
    await serve(socket, 'playback.outputs', OUTPUTS);
    await serve(socket, 'playback.state', [state('z1')]);

    expect(audio.src).toBe('');
    expect(sent(calls, 'POST', '/api/v1/playback/urls')).toEqual([]);
    // A late event of the silenced local audio does not change the zone's state.
    audio.emit('pause');
    audio.emit('timeupdate');
    await flushPromises();
    expect(wrapper.find('[data-testid="player-remote"]').text()).toContain('Spielt auf Wohnzimmer');
    expect(wrapper.find('[data-testid="player-position"]').text()).toBe('1:20');
    expect(wrapper.find('[data-testid="player-toggle"]').attributes('aria-label')).toBe('Pause');

    await wrapper.find('[data-testid="player-toggle"]').trigger('click');
    await vi.waitFor(() =>
      expect(sent(calls, 'PUT', '/api/v1/playback/state')).toEqual([
        { current_entry_id: '5', position_ms: 80_000, playing: false },
      ]),
    );
    await wrapper.find('[data-testid="player-next"]').trigger('click');
    await vi.waitFor(() =>
      expect(sent(calls, 'POST', '/api/v1/playback/skip')).toEqual([{ by: 1, playing: false }]),
    );
    await wrapper.find('[data-testid="player-zone-volume-mute"]').trigger('click');
    await vi.waitFor(() =>
      expect(sent(calls, 'PUT', '/api/v1/playback/zones/z1/volume')).toEqual([{ muted: true }]),
    );
    expect(audio.plays).toBe(0);
  });

  it('takes playback back to this device, paused at the zone position', async () => {
    const { wrapper, socket, audio, calls } = await setup();
    await serve(socket, 'playback.outputs', OUTPUTS);
    await serve(socket, 'playback.state', [state('z1')]);

    await openPicker(wrapper);
    menuItem('output-device')!.click();
    await vi.waitFor(() =>
      expect(sent(calls, 'PUT', '/api/v1/playback/output')).toEqual([{ zone_id: null }]),
    );
    await update(socket, 'playback.state', state(null, { playing: false, position: 95_000 }));

    await vi.waitFor(() => expect(audio.src).toContain('/api/v1/media/originals/a5'));
    expect(audio.plays).toBe(0);
    expect(wrapper.find('[data-testid="player-remote"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="player-position"]').text()).toBe('1:35');
  });

  it('manages rooms and their volumes', async () => {
    const { wrapper, socket, calls } = await setup();
    await serve(socket, 'playback.state', [state(null, { playing: false })]);
    await serve(socket, 'playback.outputs', OUTPUTS);

    await openPicker(wrapper);
    menuItem('output-manage')!.click();
    await vi.waitFor(() => expect(menuItem('zone-manager')).not.toBeNull());
    menuItem('room-volume-Wohnzimmer-mute')!.click();
    const kitchen = menuItem('room-zone-Küche') as HTMLSelectElement;
    kitchen.value = 'z1';
    kitchen.dispatchEvent(new Event('change'));
    const living = menuItem('room-zone-Wohnzimmer') as HTMLSelectElement;
    living.value = '';
    living.dispatchEvent(new Event('change'));

    await vi.waitFor(() => {
      expect(sent(calls, 'PUT', '/api/v1/playback/rooms/r1/volume')).toEqual([{ muted: true }]);
      expect(sent(calls, 'PUT', '/api/v1/playback/rooms/r2/zone')).toEqual([{ zone_id: 'z1' }]);
      expect(sent(calls, 'DELETE', '/api/v1/playback/rooms/r1/zone')).toEqual([null]);
    });
  });

  it('shows the systems to every user and lets admins enter addresses', async () => {
    const listener = await setup('/settings');
    await serve(listener.socket, 'playback.outputs', OUTPUTS);
    const row = listener.wrapper.find('[data-testid="output-system-192.168.1.20:47365"]');
    expect(row.text()).toContain('Erreichbar');
    expect(row.text()).toContain('Eingetragen');
    expect(listener.wrapper.find('[data-testid="output-address"]').exists()).toBe(false);
    listener.wrapper.unmount();

    const { wrapper, socket, calls } = await setup('/settings', 'admin');
    await serve(socket, 'playback.outputs', [
      { ...system, state: 'unreachable', reason: 'HTTP 503' },
    ]);
    expect(wrapper.find('[data-testid="output-system-192.168.1.20:47365"]').text()).toContain(
      'HTTP 503',
    );
    await wrapper.find('[data-testid="output-address"]').setValue('http://x/');
    await wrapper.find('form.output-settings__form').trigger('submit');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="output-problem"]').text()).toContain('keine gültige'),
    );
    await wrapper.find('[data-testid="output-address"]').setValue('192.168.1.30');
    await wrapper.find('form.output-settings__form').trigger('submit');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="output-problem"]').exists()).toBe(false),
    );

    expect(sent(calls, 'POST', '/api/v1/playback/systems')).toEqual([
      { adapter: 'raumfeld', address: 'http://x/' },
      { adapter: 'raumfeld', address: '192.168.1.30' },
    ]);
  });
});
