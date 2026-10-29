import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import { CLIENT_VERSION } from '@/version';

import { json, tokens } from './fakeServer';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

async function settings(version: string) {
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role: 'listener' })),
      'GET /api/v1/about': () =>
        json({
          version,
          build_version: 'v0.1.0',
          build_commit: '0123456789abcdef0123',
          license: 'MIT',
          source: 'https://github.com/anthology-music/anthology',
          prerelease: true,
        }),
      'GET /api/v1/about/licenses': () =>
        new Response('# Third-Party Licenses\n\n| `fastapi` | MIT |', {
          headers: { 'Content-Type': 'text/markdown' },
        }),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return wrapper;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('about', () => {
  it('shows versions, the pre-release notice and the third-party licenses', async () => {
    const wrapper = await settings(CLIENT_VERSION);
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="about-server"]').text()).toContain('v0.1.0'),
    );

    expect(wrapper.find('[data-testid="about-server"]').text()).toContain('0123456789ab');
    expect(wrapper.find('[data-testid="about-client"]').text()).toBe(CLIENT_VERSION);
    expect(wrapper.find('[data-testid="about-prerelease"]').text()).toContain('Vorabversion');
    await wrapper.find('[data-testid="about-licenses"]').trigger('click');
    await vi.waitFor(() =>
      expect(
        document.body.querySelector('[data-testid="about-licenses-dialog"]')?.textContent,
      ).toContain('# Third-Party Licenses'),
    );
  });

  it('says when the app is older or newer than the server', async () => {
    const wrapper = await settings('9.9.9');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="about-client"]').text()).toContain('neu laden'),
    );
  });
});
