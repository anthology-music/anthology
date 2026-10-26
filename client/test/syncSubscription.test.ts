import 'fake-indexeddb/auto';

import type { ServerMessage } from '@anthology/api-types';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SyncCache } from '@/sync/cache';
import { SyncClient } from '@/sync/client';
import { SyncConnection } from '@/sync/connection';
import { REFRESH_DEBOUNCE_MS } from '@/sync/subscription';

import { fakeSockets, welcome } from './fakeSocket';

const row = (id: string, name: string) => ({ id, key: [name, id], username: name });

let cacheCounter = 0;

function setup({ cache = null as SyncCache | null } = {}) {
  const sockets = fakeSockets();
  const connection = new SyncConnection({
    url: 'ws://anthology.test/api/v1/ws',
    tokens: {
      accessToken: async () => 'token',
      refresh: async () => undefined,
      onToken: () => () => undefined,
    },
    socketFactory: sockets.factory,
    random: () => 1,
  });
  const client = new SyncClient(connection, cache, () => 'user-1');
  return { sockets, connection, client };
}

async function live(sockets: ReturnType<typeof fakeSockets>) {
  sockets.latest().open();
  await vi.waitFor(() => expect(sockets.latest().last('hello')).toBeDefined());
  sockets.latest().receive(welcome());
}

function meta(sub: string, total: number, seq = 10): ServerMessage {
  return { type: 'snapshot_meta', sub, seq, data: { total, counters: {} } };
}

function chunk(sub: string, chunkNumber: number, start: number, rows: object[]): ServerMessage {
  return {
    type: 'chunk',
    sub,
    data: { chunk: chunkNumber, start, rows: rows as Record<string, unknown>[] },
  };
}

describe('subscriptions', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('subscribes with the window, shows counts and acknowledges chunks', async () => {
    const { sockets, connection, client } = setup();
    connection.start();
    await live(sockets);

    const subscription = client.subscribe('users', {}, [0, 50]);
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());
    const sub = subscription.id;
    sockets.latest().receive(meta(sub, 2));
    expect(subscription.total).toBe(2);
    sockets.latest().receive(chunk(sub, 0, 0, [row('a', 'anna'), row('b', 'ben')]));

    expect(sockets.latest().last('subscribe')?.data).toMatchObject({
      stream: 'users',
      start: 0,
      end: 50,
      since: null,
    });
    expect([...subscription.rows.values()].map((item) => item.username)).toEqual(['anna', 'ben']);
    expect(sockets.latest().last('ack')?.data.chunk).toBe(0);
  });

  it('sends a window only after subscribing', async () => {
    const { sockets, connection, client } = setup();
    const subscription = client.subscribe('users', {}, [0, 50]);
    subscription.setWindow(100, 150);
    connection.start();
    await live(sockets);
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());

    expect(sockets.latest().sent.map((message) => message.type)).toEqual(['hello', 'subscribe']);
    expect(sockets.latest().last('subscribe')?.data).toMatchObject({ start: 100, end: 150 });
  });

  it('replaces a loaded row in place when only its data changes', async () => {
    const { sockets, connection, client } = setup();
    connection.start();
    await live(sockets);
    const subscription = client.subscribe('users', {}, [0, 50]);
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());
    sockets.latest().receive(meta(subscription.id, 1));
    sockets.latest().receive(chunk(subscription.id, 0, 0, [row('a', 'anna')]));

    sockets.latest().receive({
      type: 'delta',
      sub: subscription.id,
      seq: 11,
      data: {
        op: 'upsert',
        id: 'a',
        key: ['anna', 'a'],
        row: { ...row('a', 'anna'), display_name: 'Anna B.' },
        total: 1,
      },
    });
    await vi.advanceTimersByTimeAsync(REFRESH_DEBOUNCE_MS * 2);

    expect(subscription.rows.get(0)?.display_name).toBe('Anna B.');
    expect(subscription.seq).toBe(11);
    expect(sockets.latest().last('window')).toBeUndefined();
  });

  it('re-requests the window when a delta changes the order', async () => {
    const { sockets, connection, client } = setup();
    connection.start();
    await live(sockets);
    const subscription = client.subscribe('users', {}, [0, 50]);
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());
    sockets.latest().receive(meta(subscription.id, 1));
    sockets.latest().receive(chunk(subscription.id, 0, 0, [row('b', 'ben')]));

    sockets.latest().receive({
      type: 'delta',
      sub: subscription.id,
      seq: 12,
      data: { op: 'upsert', id: 'a', key: ['anna', 'a'], row: row('a', 'anna'), total: 2 },
    });
    await vi.advanceTimersByTimeAsync(REFRESH_DEBOUNCE_MS + 10);

    expect(subscription.total).toBe(2);
    expect(sockets.latest().last('window')?.data).toEqual({ start: 0, end: 50 });
  });

  it('drops cached rows on resync', async () => {
    const { sockets, connection, client } = setup();
    connection.start();
    await live(sockets);
    const subscription = client.subscribe('users');
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());
    sockets.latest().receive(meta(subscription.id, 1));
    sockets.latest().receive(chunk(subscription.id, 0, 0, [row('a', 'anna')]));

    sockets.latest().receive({ type: 'resync', sub: subscription.id, data: {} });

    expect(subscription.rows.size).toBe(0);
  });

  it('re-subscribes with since after a reconnect', async () => {
    const { sockets, connection, client } = setup();
    connection.start();
    await live(sockets);
    const subscription = client.subscribe('users');
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());
    sockets.latest().receive(meta(subscription.id, 1, 40));

    sockets.latest().serverClose(1006);
    await vi.advanceTimersByTimeAsync(600);
    await live(sockets);

    expect(sockets.sockets).toHaveLength(2);
    expect(sockets.latest().last('subscribe')?.data.since).toBe(40);
  });
});

describe('cache', () => {
  it('shows cached rows before the server answers and resumes with since', async () => {
    cacheCounter += 1;
    const cache = new SyncCache(`test-cache-${cacheCounter}`);
    const first = setup({ cache });
    first.connection.start();
    await live(first.sockets);
    const subscription = first.client.subscribe('users', {}, [0, 50]);
    await vi.waitFor(() => expect(first.sockets.latest().last('subscribe')).toBeDefined());
    first.sockets.latest().receive(meta(subscription.id, 2, 77));
    first.sockets
      .latest()
      .receive(chunk(subscription.id, 0, 0, [row('a', 'anna'), row('b', 'ben')]));
    await vi.waitFor(async () =>
      expect(await cache.loadRows(subscription.cacheKey, 0, 50)).toHaveLength(2),
    );
    first.connection.stop();

    // Next app start: offline at first.
    const second = setup({ cache });
    const restored = second.client.subscribe('users', {}, [0, 50]);
    await vi.waitFor(() => expect(restored.rows.size).toBe(2));

    expect(restored.source).toBe('cache');
    expect(restored.total).toBe(2);
    second.connection.start();
    await live(second.sockets);
    await vi.waitFor(() => expect(second.sockets.latest().last('subscribe')).toBeDefined());
    expect(second.sockets.latest().last('subscribe')?.data.since).toBe(77);
    cache.close();
  });

  it('keeps caches of different accounts apart', async () => {
    cacheCounter += 1;
    const cache = new SyncCache(`test-cache-${cacheCounter}`);
    await cache.putMeta({ subKey: 'user-2|users|{}', total: 5, counters: {}, seq: 3 });

    const { client } = setup({ cache });
    const subscription = client.subscribe('users');
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(subscription.cacheKey).toBe('user-1|users|{}');
    expect(subscription.total).toBeNull();
    cache.close();
  });

  it('keeps uncached subscriptions out of the cache', async () => {
    cacheCounter += 1;
    const cache = new SyncCache(`test-cache-${cacheCounter}`);
    await cache.putMeta({
      subKey: 'user-1|search.tracks|{"q":"x"}',
      total: 5,
      counters: {},
      seq: 3,
    });
    const { client, connection, sockets } = setup({ cache });
    connection.start();
    await live(sockets);

    const subscription = client.subscribe('search.tracks', { q: 'x' }, [0, 50], { cache: false });
    await vi.waitFor(() => expect(sockets.latest().last('subscribe')).toBeDefined());
    sockets.latest().receive(meta(subscription.id, 1, 9));
    sockets.latest().receive(chunk(subscription.id, 0, 0, [row('a', 'anna')]));
    await vi.waitFor(() => expect(subscription.rows.size).toBe(1));

    expect(sockets.latest().last('subscribe')?.data.since ?? null).toBeNull();
    expect(await cache.loadRows(subscription.cacheKey, 0, 50)).toEqual([]);
    expect((await cache.loadMeta(subscription.cacheKey))?.seq).toBe(3);
    cache.close();
  });
});
