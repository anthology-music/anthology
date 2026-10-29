import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import { storedLanguage } from '@/i18n/language';

import { json, tokens } from './fakeServer';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

afterEach(() => {
  globalThis.localStorage.clear();
});

describe('language', () => {
  it('switches the interface language of this device and keeps it', async () => {
    const services = fakeServices(
      { 'POST /api/v1/auth/refresh': () => json(tokens({ role: 'listener' })) },
      { 'anthology.refreshToken': 'device-1.stored' },
    );
    const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
    const socket = services.sockets.latest();
    socket.open();
    await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
    socket.receive(welcome());
    await flushPromises();

    expect(storedLanguage()).toBe('de');
    expect(wrapper.find('#language-title').text()).toBe('Sprache');
    await wrapper.find('[data-testid="language-en"] input').setValue(true);

    expect(wrapper.find('#language-title').text()).toBe('Language');
    expect(storedLanguage()).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });
});
