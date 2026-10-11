import { describe, expect, it } from 'vitest';

import App from '@/App.vue';

import { mountWithApp } from './mount';

function labels(wrapper: Awaited<ReturnType<typeof mountWithApp>>): string[] {
  return wrapper.findAll('nav .sidebar__label').map((label) => label.text());
}

describe('MainLayout', () => {
  it('shows the navigation in German by default', async () => {
    const wrapper = await mountWithApp(App);

    expect(labels(wrapper)).toEqual(['Streaming', 'Lokal', 'Werke', 'Einstellungen']);
    expect(wrapper.find('nav').attributes('aria-label')).toBe('Hauptnavigation');
  });

  it('shows the navigation in English', async () => {
    const wrapper = await mountWithApp(App, { locale: 'en' });

    expect(labels(wrapper)).toEqual(['Streaming', 'Local', 'Works', 'Settings']);
  });

  it('marks the current page as active and shows its header', async () => {
    const wrapper = await mountWithApp(App, { path: '/works' });

    expect(wrapper.find('.sidebar__link--active .sidebar__label').text()).toBe('Werke');
    expect(wrapper.find('h1').text()).toBe('Werke');
  });

  it('redirects the start page to the library', async () => {
    const wrapper = await mountWithApp(App, { path: '/' });

    expect(wrapper.find('h1').text()).toBe('Lokal');
  });

  it('shows the connection state as text, not only as colour', async () => {
    const wrapper = await mountWithApp(App);

    expect(wrapper.find('[role="status"]').text()).toBe('Nicht verbunden');
  });
});
