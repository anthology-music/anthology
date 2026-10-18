import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import { fakeServices, mountWithApp } from './mount';

async function fill(wrapper: Awaited<ReturnType<typeof mountWithApp>>, values: string[]) {
  const inputs = wrapper.findAll('input');
  for (const [index, value] of values.entries()) await inputs[index]!.setValue(value);
  await wrapper.find('form').trigger('submit');
  await flushPromises();
}

describe('authentication pages', () => {
  it('sends a fresh installation to the setup page', async () => {
    fakeServices({ 'GET /api/v1/setup': () => json({ required: true }) });

    const wrapper = await mountWithApp(App, { path: '/local', guard: true });

    expect(wrapper.router.currentRoute.value.name).toBe('setup');
    expect(wrapper.find('h1').text()).toBe('Anthology einrichten');
  });

  it('sends a signed-out user to the sign-in page and back after signing in', async () => {
    fakeServices({
      'GET /api/v1/setup': () => json({ required: false }),
      'POST /api/v1/auth/login': () => json(tokens()),
    });
    const wrapper = await mountWithApp(App, { path: '/works', guard: true });
    expect(wrapper.router.currentRoute.value.name).toBe('login');

    await fill(wrapper, ['admin', 'correct horse']);

    await vi.waitFor(() => expect(wrapper.router.currentRoute.value.path).toBe('/works'));
  });

  it('shows wrong credentials as an alert with text', async () => {
    fakeServices({
      'GET /api/v1/setup': () => json({ required: false }),
      'POST /api/v1/auth/login': () => json({ detail: 'invalid_credentials' }, 401),
    });
    const wrapper = await mountWithApp(App, { path: '/login', guard: true });

    await fill(wrapper, ['admin', 'wrong password']);

    expect(wrapper.find('[role="alert"]').text()).toContain(
      'Benutzername oder Passwort ist falsch.',
    );
    expect(wrapper.router.currentRoute.value.name).toBe('login');
  });

  it('creates the first account in the setup and opens the library', async () => {
    let body: Record<string, unknown> = {};
    fakeServices({
      'GET /api/v1/setup': () => json({ required: true }),
      'POST /api/v1/setup': async (request) => {
        body = (await request.json()) as Record<string, unknown>;
        return json(tokens(), 201);
      },
    });
    const wrapper = await mountWithApp(App, { path: '/setup', guard: true });

    await fill(wrapper, ['Lukas', 'lukas', 'correct horse']);

    expect(body).toMatchObject({ username: 'lukas', display_name: 'Lukas' });
    await vi.waitFor(() => expect(wrapper.router.currentRoute.value.path).toBe('/local/albums'));
  });

  it('restores a stored session without showing the sign-in page', async () => {
    fakeServices(
      { 'POST /api/v1/auth/refresh': () => json(tokens()) },
      { 'anthology.refreshToken': 'device-1.stored' },
    );

    const wrapper = await mountWithApp(App, { path: '/settings', guard: true });

    expect(wrapper.router.currentRoute.value.name).toBe('settings');
  });
});
