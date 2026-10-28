import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { Quasar } from 'quasar';
import type { Component } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import { createApi } from '@/api/client';
import { useAuthStore } from '@/features/users/store';
import { useSyncStore } from '@/sync/store';
import { AuthSession } from '@/features/users/session';
import { createAppI18n, type MessageLanguages } from '@/i18n/setup';
import { memoryStorage } from '@/platform/storage';
import { installAuthGuard } from '@/router/guards';
import routes from '@/router/routes';
import { connectSyncToSession, setServices } from '@/services';
import { SyncClient } from '@/sync/client';
import { SyncConnection } from '@/sync/connection';

import { fakeFetch, type Handler } from './fakeServer';
import { fakeSockets } from './fakeSocket';

export const BASE = 'http://anthology.test';

/** Services backed by a scripted fake server. */
export function fakeServices(
  routesByPath: Record<string, Handler> = {},
  stored: Record<string, string> = {},
) {
  const server = fakeFetch(routesByPath);
  const sockets = fakeSockets();
  const session = new AuthSession(memoryStorage(stored), { baseUrl: BASE, fetch: server.fetch });
  const connection = new SyncConnection({
    url: 'ws://anthology.test/api/v1/ws',
    tokens: session,
    socketFactory: sockets.factory,
    random: () => 1,
  });
  const sync = new SyncClient(connection, null, () => session.state.user?.id ?? 'anonymous');
  connectSyncToSession(session, sync);
  const services = {
    session,
    api: createApi(session, { baseUrl: BASE, fetch: server.fetch }),
    sync,
  };
  setServices(services);
  return { ...services, server, sockets };
}

/** Mount a component with Quasar, i18n, Pinia and the app routes (memory history). */
export async function mountWithApp(
  component: Component,
  {
    locale = 'de',
    path = '/local',
    guard = false,
    props = {},
  }: {
    locale?: MessageLanguages;
    path?: string;
    guard?: boolean;
    props?: Record<string, unknown>;
  } = {},
) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().bind();
  useSyncStore().bind();
  const router = createRouter({ history: createMemoryHistory(), routes });
  if (guard) installAuthGuard(router);
  await router.push(path);
  await router.isReady();
  const wrapper = mount(component, {
    props,
    global: { plugins: [Quasar, createAppI18n(locale), router, pinia] },
  });
  await flushPromises();
  return Object.assign(wrapper, { router });
}
