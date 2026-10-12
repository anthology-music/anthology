import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createApi } from '@/api/client';
import { AuthSession, REFRESH_MARGIN_MS } from '@/features/users/session';
import { memoryStorage } from '@/platform/storage';

import { fakeFetch, json, tokens } from './fakeServer';

const BASE = 'http://anthology.test';

function session(routes: Parameters<typeof fakeFetch>[0], stored: Record<string, string> = {}) {
  const server = fakeFetch(routes);
  const storage = memoryStorage(stored);
  return {
    auth: new AuthSession(storage, { baseUrl: BASE, fetch: server.fetch }),
    server,
    storage,
  };
}

describe('AuthSession', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it('signs in, stores the refresh token and device ID, and reports the user', async () => {
    const { auth, storage } = session({ 'POST /api/v1/auth/login': () => json(tokens()) });
    const changes: (string | undefined)[] = [];
    auth.onChange((state) => changes.push(state.user?.username));

    await auth.login('admin', 'secret');

    expect(auth.signedIn).toBe(true);
    expect(storage.get('anthology.refreshToken')).toMatch(/^device-1\.refresh-/);
    expect(storage.get('anthology.deviceId')).toBe('device-1');
    expect(changes).toEqual(['admin']);
  });

  it('sends the stored device ID when signing in again', async () => {
    let sent: unknown;
    const { auth } = session(
      {
        'POST /api/v1/auth/login': async (request) => {
          sent = ((await request.json()) as { device: { id: string } }).device.id;
          return json(tokens());
        },
      },
      { 'anthology.deviceId': 'device-1' },
    );

    await auth.login('admin', 'secret');

    expect(sent).toBe('device-1');
  });

  it('reports wrong credentials', async () => {
    const { auth } = session({ 'POST /api/v1/auth/login': () => json({ detail: 'x' }, 401) });

    await expect(auth.login('admin', 'wrong')).rejects.toMatchObject({
      code: 'invalid_credentials',
    });
  });

  it('refreshes before the access token expires', async () => {
    const { auth, server } = session({
      'POST /api/v1/auth/login': () => json(tokens({ expiresInMs: REFRESH_MARGIN_MS + 5_000 })),
      'POST /api/v1/auth/refresh': () => json(tokens()),
    });
    const renewed: string[] = [];
    auth.onToken((token) => renewed.push(token));
    await auth.login('admin', 'secret');

    await vi.advanceTimersByTimeAsync(6_000);

    expect(server.calls.filter((call) => call.endsWith('/refresh'))).toHaveLength(1);
    expect(renewed).toHaveLength(2);
  });

  it('runs concurrent refreshes as one request', async () => {
    const { auth, server } = session(
      { 'POST /api/v1/auth/refresh': () => json(tokens()) },
      { 'anthology.refreshToken': 'device-1.old' },
    );

    await Promise.all([auth.accessToken(), auth.accessToken(), auth.refresh()]);

    expect(server.calls).toEqual(['POST /api/v1/auth/refresh']);
  });

  it('signs out locally when the refresh token is rejected', async () => {
    const { auth, storage } = session(
      { 'POST /api/v1/auth/refresh': () => json({ detail: 'invalid_refresh_token' }, 401) },
      { 'anthology.refreshToken': 'device-1.stolen', 'anthology.deviceId': 'device-1' },
    );

    expect(await auth.restore()).toBe(false);
    expect(auth.signedIn).toBe(false);
    expect(storage.get('anthology.refreshToken')).toBeNull();
    expect(storage.get('anthology.deviceId')).toBe('device-1');
  });

  it('keeps the session when the server is unreachable during a refresh', async () => {
    const { auth, storage } = session(
      { 'POST /api/v1/auth/refresh': () => json({ detail: 'down' }, 503) },
      { 'anthology.refreshToken': 'device-1.valid' },
    );

    await expect(auth.refresh()).rejects.toMatchObject({ code: 'server_unreachable' });
    expect(storage.get('anthology.refreshToken')).toBe('device-1.valid');
  });

  it('logout forgets the session and tells the server', async () => {
    const { auth, server } = session({
      'POST /api/v1/auth/login': () => json(tokens()),
      'POST /api/v1/auth/logout': () => new Response(null, { status: 204 }),
    });
    await auth.login('admin', 'secret');

    await auth.logout();

    expect(auth.signedIn).toBe(false);
    expect(server.calls).toContain('POST /api/v1/auth/logout');
  });
});

describe('createApi', () => {
  it('adds the access token and retries once after a 401', async () => {
    let attempts = 0;
    const server = fakeFetch({
      'POST /api/v1/auth/login': () => json(tokens()),
      'POST /api/v1/auth/refresh': () => json(tokens()),
      'GET /api/v1/me': (request) => {
        attempts += 1;
        expect(request.headers.get('Authorization')).toMatch(/^Bearer access-/);
        return attempts === 1 ? json({ detail: 'expired' }, 401) : json(tokens().user);
      },
    });
    const auth = new AuthSession(memoryStorage(), { baseUrl: BASE, fetch: server.fetch });
    await auth.login('admin', 'secret');
    const api = createApi(auth, { baseUrl: BASE, fetch: server.fetch });

    const { data } = await api.GET('/api/v1/me');

    expect(data?.username).toBe('admin');
    expect(attempts).toBe(2);
    expect(server.calls.filter((call) => call.endsWith('/refresh'))).toHaveLength(1);
  });
});
