import { mount } from '@vue/test-utils';
import { Quasar } from 'quasar';
import type { Component } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';

import routes from '@/router/routes';
import { createAppI18n, type MessageLanguages } from '@/i18n/setup';

/** Mount a component with Quasar, i18n and the app routes (memory history). */
export async function mountWithApp(
  component: Component,
  { locale = 'de', path = '/local' }: { locale?: MessageLanguages; path?: string } = {},
) {
  const router = createRouter({ history: createMemoryHistory(), routes });
  await router.push(path);
  await router.isReady();
  return mount(component, {
    global: { plugins: [Quasar, createAppI18n(locale), router] },
  });
}
