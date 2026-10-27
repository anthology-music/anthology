import type { PlayQueueStateRow, Schemas } from '@anthology/api-types';
import { defineStore } from 'pinia';
import { computed, reactive, ref, shallowRef } from 'vue';

import { getServices } from '@/services';
import type { Subscription } from '@/sync/subscription';

import { type AudioLike, createAudio } from './audio';
import { playableFormats } from './formats';

export type PlayRule = NonNullable<Schemas['StartIn']['rule']>;
export type Problem = 'unplayable' | 'missing';

/** Report the position this often while playing (spec: playback, Resume). */
export const REPORT_MS = 15_000;
/** URLs are renewed when they expire within this time (spec: Short-lived client media URLs). */
export const RENEW_MS = 5 * 60_000;
/** "Previous" restarts the track after this much of it (spec: Player controls). */
export const RESTART_MS = 3_000;

interface SignedUrl {
  url: string | null;
  expires: number;
}

/**
 * The player of this device: the queue lives on the server (`playback.state` with the
 * current entry), the audio plays here. Starting, skipping and reporting go over REST; the
 * state stream answers with the new current entry, which the player then loads.
 */
export const usePlayerStore = defineStore('player', () => {
  const state = shallowRef<PlayQueueStateRow | null>(null);
  const loaded = ref<string | null>(null);
  const playing = ref(false);
  const positionMs = ref(0);
  const durationMs = ref(0);
  const volume = ref(1);
  const problems = reactive(new Map<string, Problem>());
  const message = ref<'shortened' | null>(null);

  let audio: AudioLike | null = null;
  let subscription: Subscription | null = null;
  let stopListening: (() => void) | null = null;
  let reportTimer: ReturnType<typeof setInterval> | null = null;
  let formats = new Set<string>();
  // The user wants sound: play what gets loaded (false after a reload: resume paused).
  let wanted = false;
  let pendingSeek: number | null = null;
  const urls = new Map<string, SignedUrl>();
  const now = () => Date.now();

  const current = computed(() => state.value?.current ?? null);

  function api() {
    return getServices().api;
  }

  // --- audio ------------------------------------------------------------------------------

  function attach(): AudioLike {
    if (audio) return audio;
    const element = createAudio();
    formats = playableFormats(element);
    element.volume = volume.value;
    element.addEventListener('timeupdate', () => {
      positionMs.value = Math.round(element.currentTime * 1000);
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
      playing.value = true;
    });
    element.addEventListener('pause', () => {
      playing.value = false;
    });
    element.addEventListener('ended', () => {
      void step(1);
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
      if (playing.value) void report();
    }, REPORT_MS);
  }

  function stop(): void {
    stopListening?.();
    if (subscription) getServices().sync.unsubscribe(subscription);
    subscription = null;
    if (reportTimer) clearInterval(reportTimer);
    reportTimer = null;
    audio?.pause();
  }

  function onState(): void {
    const row = (subscription?.rows.get(0) as PlayQueueStateRow | undefined) ?? null;
    state.value = subscription?.total === 0 ? null : row;
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
    const format = current.value?.format ?? null;
    if (format === null) problems.set(entry, 'missing');
    else if (!formats.has(format)) problems.set(entry, 'unplayable');
    if (problems.has(entry)) {
      element.pause();
      await advance();
      return;
    }
    const next = state.value?.next_entry_id;
    const known = await signed(next ? [entry, next] : [entry]);
    if (loaded.value !== entry) return;
    const url = known.get(entry)?.url ?? null;
    if (url === null) {
      problems.set(entry, 'missing');
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
    if ((audio?.currentTime ?? 0) * 1000 > RESTART_MS) {
      await seek(0);
      return;
    }
    await step(-1);
  }

  async function seek(ms: number): Promise<void> {
    if (audio) audio.currentTime = ms / 1000;
    positionMs.value = ms;
    await report();
  }

  function setVolume(value: number): void {
    volume.value = value;
    if (audio) audio.volume = value;
  }

  // --- starting playback -------------------------------------------------------------------

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
  };
});
