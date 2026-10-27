import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

const SETTINGS = {
  audio_bitrate: 'original',
  offline_bitrate: null,
  max_video_resolution: 1080,
  offline_limit_bytes: null,
  wifi_only_sync: true,
  videos_wifi_only: true,
  default_output: null,
  view_prefs_json: '{}',
};

describe('playback settings', () => {
  it('saves the bitrate of this device', async () => {
    const saved: unknown[] = [];
    const services = fakeServices(
      {
        'POST /api/v1/auth/refresh': () => json(tokens({ role: 'listener' })),
        'GET /api/v1/me/device-settings': () => json(SETTINGS),
        'PUT /api/v1/me/device-settings': async (request) => {
          const body: unknown = await request.json();
          saved.push(body);
          return json(body);
        },
      },
      { 'anthology.refreshToken': 'device-1.stored' },
    );
    const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
    const socket = services.sockets.latest();
    socket.open();
    await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
    socket.receive(welcome());
    await flushPromises();
    await vi.waitFor(() =>
      expect(
        (wrapper.find('[data-testid="bitrate-original"] input').element as HTMLInputElement)
          .checked,
      ).toBe(true),
    );

    await wrapper.find('[data-testid="bitrate-128"] input').trigger('change');
    await vi.waitFor(() => expect(saved).toHaveLength(1));

    expect(saved[0]).toEqual({ ...SETTINGS, audio_bitrate: '128' });
    expect(wrapper.find('[data-testid="bitrate-message"]').text()).toContain('Gespeichert');
  });
});
