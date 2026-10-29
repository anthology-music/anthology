import type { PlayQueueStateRow, Schemas } from '@anthology/api-types';
import { defineStore } from 'pinia';
import { computed, reactive, ref, shallowRef } from 'vue';

import { getServices } from '@/services';
import type { Subscription } from '@/sync/subscription';

import { type AudioLike, createAudio } from './audio';

export type PlayRule = NonNullable<Schemas['StartIn']['rule']>;
export type Problem = 'unplayable' | 'missing';

/** Report the position this often while playing (spec: playback, Resume). */
export const REPORT_MS = 15_000;
/** URLs are renewed when they expire within this time (spec: Short-lived client media URLs). */
export const RENEW_MS = 5 * 60_000;
/** "Previous" restarts the track after this much of it (spec: Player controls). */
export const RESTART_MS = 3_000;
/** While a zone plays, the shown position advances this often between server reports. */
export const REMOTE_TICK_MS = 500;

interface SignedUrl {
  url: string | null;
  expires: number;
}

/**
 * The player of this device: the queue lives on the server (`playback.state` with the
 * current entry), the audio plays here. Starting, skipping and reporting go over REST; the
 * state stream answers with the new current entry, which the player then loads.
 *
 * While the device controls an output zone (`output_zone_id`), it is a remote control (spec:
 * Remote control): no audio plays here, the state shows the zone's queue, and play, pause,
 * seek and skip change the zone's queue, which the server's zone player carries out.
 */
export const usePlayerStore = defineStore('player', () => {
  const state = shallowRef<PlayQueueStateRow | null>(null);
  const loaded = ref<string | null>(null);
  const playing = ref(false);
  const positionMs = ref(0);
  const durationMs = ref(0);
  const volume = ref(1);
  const problems = reactive(new Map<string, Problem>());
  const message = ref<'shortened' | 'output_offline' | 'output_failed' | null>(null);

  let audio: AudioLike | null = null;
  let subscription: Subscription | null = null;
  let stopListening: (() => void) | null = null;
  let reportTimer: ReturnType<typeof setInterval> | null = null;
  // The user wants sound: play what gets loaded (false after a reload: resume paused).
  let wanted = false;
  let pendingSeek: number | null = null;
  const urls = new Map<string, SignedUrl>();
  const now = () => Date.now();
  // Remote control: the zone's position at the time it arrived.
  let remoteAt = 0;
  let remoteTimer: ReturnType<typeof setInterval> | null = null;

  const current = computed(() => state.value?.current ?? null);
  /** The zone this device controls; null: it plays itself. */
  const outputZone = computed(() => state.value?.output_zone_id ?? null);

  function api() {
    return getServices().api;
  }

  // --- audio ------------------------------------------------------------------------------

  function attach(): AudioLike {
    if (audio) return audio;
    const element = createAudio();
    element.volume = volume.value;
    // While a zone plays, the state comes from the zone queue: events of the silenced local
    // audio (a late `pause` after the handover) must not change it.
    const local = () => outputZone.value === null;
    element.addEventListener('timeupdate', () => {
      if (local()) positionMs.value = Math.round(element.currentTime * 1000);
    });
    element.addEventListener('durationchange', () => {
      durationMs.value = Number.isFinite(element.duration)
        ? Math.round(element.duration * 1000)
        : 0;
    });
    element.addEventListener('loadedmetadata', () => {
      if (pendingSeek !== null) element.currentTime = pendingSeek / 1000;
      pendingSeek = null;
    });
    element.addEventListener('play', () => {
      if (local()) playing.value = true;
    });
    element.addEventListener('pause', () => {
      if (local()) playing.value = false;
    });
    element.addEventListener('ended', () => {
      if (local()) void step(1);
    });
    element.addEventListener('error', () => {
      if (loaded.value) problems.set(loaded.value, 'missing');
      void advance();
    });
    audio = element;
    mediaSession();
    return element;
  }

  // --- state from the server ------------------------------------------------------------

  function start(): void {
    if (subscription) return;
    attach();
    subscription = getServices().sync.subscribe('playback.state', {}, [0, 1], { cache: false });
    stopListening = subscription.onChange(() => onState());
    reportTimer = setInterval(() => {
      if (playing.value && !outputZone.value) void report();
    }, REPORT_MS);
    remoteTimer = setInterval(() => {
      if (outputZone.value && playing.value) {
        positionMs.value = Math.min(
          (state.value?.position_ms ?? 0) + (now() - remoteAt),
          durationMs.value || Number.MAX_SAFE_INTEGER,
        );
      }
    }, REMOTE_TICK_MS);
  }

  function stop(): void {
    stopListening?.();
    if (subscription) getServices().sync.unsubscribe(subscription);
    subscription = null;
    if (reportTimer) clearInterval(reportTimer);
    reportTimer = null;
    if (remoteTimer) clearInterval(remoteTimer);
    remoteTimer = null;
    audio?.pause();
  }

  function onState(): void {
    const row = (subscription?.rows.get(0) as PlayQueueStateRow | undefined) ?? null;
    const wasRemote = outputZone.value !== null;
    state.value = subscription?.total === 0 ? null : row;
    if (row?.output_zone_id) {
      remote(row);
      return;
    }
    if (wasRemote) {
      // Playback came back to this device: load where the zone stopped, paused.
      loaded.value = null;
      wanted = false;
      if (audio) audio.src = '';
    }
    const entry = row?.current_entry_id ?? null;
    if (entry === null) {
      if (loaded.value !== null) {
        audio?.pause();
        loaded.value = null;
      }
      return;
    }
    if (entry !== loaded.value) void load(entry, loaded.value === null ? row!.position_ms : 0);
  }

  /** Show the zone's state; the audio of this device stays silent. */
  function remote(row: PlayQueueStateRow): void {
    if (audio && !audio.paused) audio.pause();
    wanted = false;
    loaded.value = row.current_entry_id;
    playing.value = row.playing;
    positionMs.value = row.position_ms;
    durationMs.value = row.current?.duration_ms ?? 0;
    remoteAt = now();
    updateMetadata();
  }

  /** Commands of the remote control: the zone queue's new state. */
  async function command(change: { positionMs?: number; playing?: boolean }): Promise<void> {
    const row = state.value;
    if (!row?.current_entry_id) return;
    const position = change.positionMs ?? positionMs.value;
    const wantPlaying = change.playing ?? playing.value;
    positionMs.value = position;
    playing.value = wantPlaying;
    await api().PUT('/api/v1/playback/state', {
      body: { current_entry_id: row.current_entry_id, position_ms: position, playing: wantPlaying },
    });
  }

  async function signed(ids: string[]): Promise<Map<string, SignedUrl>> {
    const missing = ids.filter((id) => {
      const known = urls.get(id);
      return !known || known.expires - now() < RENEW_MS;
    });
    if (missing.length) {
      const { data } = await api().POST('/api/v1/playback/urls', {
        body: { entry_ids: missing },
      });
      for (const item of data ?? []) {
        urls.set(item.entry_id, {
          url: item.url,
          expires: item.expires_at ? Date.parse(item.expires_at) : now(),
        });
      }
    }
    return urls;
  }

  async function load(entry: string, fromMs: number): Promise<void> {
    const element = attach();
    loaded.value = entry;
    positionMs.value = fromMs;
    durationMs.value = current.value?.duration_ms ?? 0;
    updateMetadata();
    if ((current.value?.format ?? null) === null) {
      problems.set(entry, 'missing');
      element.pause();
      await advance();
      return;
    }
    const next = state.value?.next_entry_id;
    const known = await signed(next ? [entry, next] : [entry]);
    if (loaded.value !== entry) return;
    const url = known.get(entry)?.url ?? null;
    if (url === null) {
      // The server found no delivery: its transcode failed (spec: Formats the device cannot
      // play).
      problems.set(entry, 'unplayable');
      element.pause();
      await advance();
      return;
    }
    pendingSeek = fromMs > 0 ? fromMs : null;
    element.src = url;
    if (wanted) await element.play().catch(() => undefined);
  }

  /** Past an entry that cannot play: on to the next one while the user wants sound. */
  async function advance(): Promise<void> {
    if (wanted) await step(1);
  }

  async function step(by: 1 | -1): Promise<void> {
    if (outputZone.value) {
      await api().POST('/api/v1/playback/skip', { body: { by, playing: playing.value } });
      return;
    }
    const { data } = await api().POST('/api/v1/playback/skip', {
      body: { by, playing: wanted },
    });
    // At the end of the queue the server keeps the last entry and stops.
    if (by === 1 && data && data.current_entry_id === loaded.value) {
      wanted = false;
      audio?.pause();
      if (audio) audio.currentTime = 0;
    }
  }

  async function report(): Promise<void> {
    if (!loaded.value) return;
    await api().PUT('/api/v1/playback/state', {
      body: {
        current_entry_id: loaded.value,
        // Before the file is loaded, the position to resume at is still pending.
        position_ms: pendingSeek ?? Math.round((audio?.currentTime ?? 0) * 1000),
        playing: wanted,
      },
    });
  }

  // --- controls ---------------------------------------------------------------------------

  async function play(): Promise<void> {
    if (outputZone.value) {
      await command({ playing: true });
      return;
    }
    wanted = true;
    const element = attach();
    if (loaded.value && problems.has(loaded.value)) {
      await advance();
      return;
    }
    if (!element.src && loaded.value) await load(loaded.value, positionMs.value);
    else await element.play().catch(() => undefined);
    await report();
  }

  async function pause(): Promise<void> {
    if (outputZone.value) {
      await command({ playing: false });
      return;
    }
    wanted = false;
    audio?.pause();
    await report();
  }

  async function toggle(): Promise<void> {
    await (playing.value ? pause() : play());
  }

  async function next(): Promise<void> {
    await step(1);
  }

  async function previous(): Promise<void> {
    const at = outputZone.value ? positionMs.value : (audio?.currentTime ?? 0) * 1000;
    if (at > RESTART_MS) {
      await seek(0);
      return;
    }
    await step(-1);
  }

  async function seek(ms: number): Promise<void> {
    if (outputZone.value) {
      await command({ positionMs: ms });
      return;
    }
    if (audio) audio.currentTime = ms / 1000;
    positionMs.value = ms;
    await report();
  }

  function setVolume(value: number): void {
    volume.value = value;
    if (audio) audio.volume = value;
  }

  // --- starting playback -------------------------------------------------------------------

  /** Hand this device's queue to a zone, or take it back (null; spec: Output picker). */
  async function selectOutput(zoneId: string | null): Promise<boolean> {
    if (zoneId === null) wanted = false;
    const { error, response } = await api().PUT('/api/v1/playback/output', {
      body: { zone_id: zoneId },
    });
    if (response.ok) {
      message.value = null;
      return true;
    }
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    message.value = detail === 'output_offline' ? 'output_offline' : 'output_failed';
    return false;
  }

  async function startQueue(body: Schemas['StartIn']): Promise<void> {
    attach();
    if (body.mode === undefined || body.mode === 'replace') wanted = true;
    const { data } = await api().POST('/api/v1/playback/queue', { body });
    message.value = data?.shortened ? 'shortened' : null;
  }

  const playList = (rule: PlayRule, start?: string) =>
    startQueue({ mode: 'replace', rule, start: start ?? null });
  const playTracks = (ids: string[], start?: string) =>
    startQueue({ mode: 'replace', ids, start: start ?? null });
  const enqueue = (mode: 'next' | 'append', ids: string[]) => startQueue({ mode, ids });

  async function playEntry(entry: string): Promise<void> {
    wanted = true;
    await api().PUT('/api/v1/playback/state', {
      body: { current_entry_id: entry, position_ms: 0, playing: true },
    });
  }

  async function removeEntry(entry: string): Promise<void> {
    await api().DELETE('/api/v1/playback/queue/entries/{entry_id}', {
      params: { path: { entry_id: entry } },
    });
  }

  // --- operating system ----------------------------------------------------------------

  function mediaSession(): void {
    const session = globalThis.navigator?.mediaSession;
    if (!session) return;
    session.setActionHandler('play', () => void play());
    session.setActionHandler('pause', () => void pause());
    session.setActionHandler('nexttrack', () => void next());
    session.setActionHandler('previoustrack', () => void previous());
    session.setActionHandler('seekto', (details) => {
      if (details.seekTime !== undefined) void seek(details.seekTime * 1000);
    });
  }

  function updateMetadata(): void {
    const session = globalThis.navigator?.mediaSession;
    const track = current.value;
    if (!session || !track || typeof MediaMetadata === 'undefined') return;
    session.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist,
      album: track.album,
    });
  }

  return {
    state,
    current,
    outputZone,
    loaded,
    playing,
    positionMs,
    durationMs,
    volume,
    problems,
    message,
    start,
    stop,
    play,
    pause,
    toggle,
    next,
    previous,
    seek,
    setVolume,
    playList,
    playTracks,
    enqueue,
    playEntry,
    removeEntry,
    selectOutput,
  };
});
