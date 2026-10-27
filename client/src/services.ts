import { createApi, type Api } from '@/api/client';
import { playableFormats } from '@/features/playback/formats';
import { AuthSession } from '@/features/users/session';
import { browserStorage } from '@/platform/storage';
import { SyncCache } from '@/sync/cache';
import { SyncClient } from '@/sync/client';
import { SyncConnection } from '@/sync/connection';

/** Application-wide service instances (one per app; tests create their own). */
export interface Services {
  session: AuthSession;
  api: Api;
  sync: SyncClient;
}

let services: Services | null = null;

function websocketUrl(): string {
  const { protocol, host } = globalThis.location;
  return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}/api/v1/ws`;
}

/** Start the sync connection while signed in, stop it when signed out. */
export function connectSyncToSession(session: AuthSession, sync: SyncClient): void {
  const update = () => (session.signedIn ? sync.connection.start() : sync.connection.stop());
  session.onChange(update);
  update();
}

let formats: string[] | null = null;

export function getServices(): Services {
  if (!services) {
    const session = new AuthSession(browserStorage);
    const connection = new SyncConnection({
      url: websocketUrl(),
      tokens: session,
      deviceId: () => session.state.deviceId,
      formats: () => (formats ??= typeof Audio === 'undefined' ? null : playableFormats()),
    });
    const cache = typeof indexedDB === 'undefined' ? null : new SyncCache();
    const sync = new SyncClient(connection, cache, () => session.state.user?.id ?? 'anonymous');
    connectSyncToSession(session, sync);
    services = { session, api: createApi(session), sync };
  }
  return services;
}

export function setServices(value: Services | null): void {
  services = value;
}
