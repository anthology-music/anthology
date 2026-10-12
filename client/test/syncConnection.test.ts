import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SyncConnection, type ConnectionState, type TokenSource } from '@/sync/connection';

import { fakeSockets, welcome } from './fakeSocket';

function tokenSource(overrides: Partial<TokenSource> = {}) {
  const listeners = new Set<(token: string) => void>();
  let current = 'token-1';
  const source: TokenSource & { renew(token: string): void } = {
    accessToken: vi.fn(async () => current),
    refresh: vi.fn(async () => {
      current = 'token-refreshed';
    }),
    onToken: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    renew(token: string) {
      current = token;
      for (const listener of listeners) listener(token);
    },
    ...overrides,
  };
  return source;
}

function connection(tokens = tokenSource()) {
  const sockets = fakeSockets();
  const conn = new SyncConnection({
    url: 'ws://anthology.test/api/v1/ws',
    tokens,
    deviceId: () => 'device-1',
    socketFactory: sockets.factory,
    random: () => 1,
  });
  const states: ConnectionState[] = [];
  conn.onState((state) => states.push(state));
  return { conn, sockets, tokens, states };
}

async function goLive(sockets: ReturnType<typeof fakeSockets>) {
  sockets.latest().open();
  await vi.waitFor(() => expect(sockets.latest().last('hello')).toBeDefined());
  sockets.latest().receive(welcome());
}

describe('SyncConnection', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('sends hello with token and device and becomes live after welcome', async () => {
    const { conn, sockets, states } = connection();
    conn.start();

    await goLive(sockets);

    expect(sockets.latest().last('hello')?.data).toMatchObject({
      protocol: 1,
      token: 'token-1',
      device_id: 'device-1',
    });
    expect(states).toEqual(['connecting', 'live']);
  });

  it('renews the token on the open connection with auth', async () => {
    const { conn, sockets, tokens } = connection();
    conn.start();
    await goLive(sockets);

    tokens.renew('token-2');

    expect(sockets.latest().last('auth')?.data.token).toBe('token-2');
  });

  it('reconnects with growing delays after the connection drops', async () => {
    const { conn, sockets, states } = connection();
    conn.start();
    await goLive(sockets);

    sockets.latest().serverClose(1006);
    expect(states.at(-1)).toBe('reconnecting');
    await vi.advanceTimersByTimeAsync(499);
    expect(sockets.sockets).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(sockets.sockets).toHaveLength(2);

    sockets.latest().serverClose(1006);
    await vi.advanceTimersByTimeAsync(999);
    expect(sockets.sockets).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(sockets.sockets).toHaveLength(3);

    await goLive(sockets);
    expect(states.at(-1)).toBe('live');
  });

  it('refreshes the token and reconnects after 4401', async () => {
    const { conn, sockets, tokens } = connection();
    conn.start();
    await goLive(sockets);

    sockets.latest().serverClose(4401);
    await vi.waitFor(() => expect(sockets.sockets).toHaveLength(2));
    await goLive(sockets);

    expect(tokens.refresh).toHaveBeenCalledOnce();
    expect(sockets.latest().last('hello')?.data.token).toBe('token-refreshed');
  });

  it('stops and reports an outdated app after 4426', async () => {
    const { conn, sockets, states } = connection();
    conn.start();
    sockets.latest().open();

    sockets.latest().serverClose(4426);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(states.at(-1)).toBe('outdated');
    expect(sockets.sockets).toHaveLength(1);
  });

  it('goes offline without a session', async () => {
    const { conn, sockets, states } = connection(tokenSource({ accessToken: async () => null }));
    conn.start();

    sockets.latest().open();
    await vi.waitFor(() => expect(states.at(-1)).toBe('offline'));

    expect(sockets.latest().closedByClient).toBe(1000);
  });

  it('does not send messages while not live', () => {
    const { conn } = connection();
    conn.start();

    expect(conn.send({ type: 'ack', sub: 's1', data: { chunk: 0 } })).toBe(false);
  });
});
