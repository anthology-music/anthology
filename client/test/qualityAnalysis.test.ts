import type { ClientMessage } from '@anthology/api-types';
import { flushPromises, mount } from '@vue/test-utils';
import { Quasar } from 'quasar';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';
import QualityBadge from '@/features/library/components/QualityBadge.vue';
import { createAppI18n } from '@/i18n/setup';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;
type BadgeProps = InstanceType<typeof QualityBadge>['$props'];

function badge(props: BadgeProps) {
  return mount(QualityBadge, { props, global: { plugins: [Quasar, createAppI18n('de')] } });
}

describe('quality badge', () => {
  it('shows nothing before a conclusive analysis', () => {
    expect(badge({ effective: null, status: null }).text()).toBe('');
  });

  it('shows the effective quality, with a warning for upscaled files', () => {
    const genuine = badge({ effective: 'hires_lossless', status: 'genuine' });
    const upscaled = badge({ effective: 'lossy_low', status: 'upscaled' });

    expect(genuine.find('[data-testid="quality-badge"]').text()).toBe('Hi-Res');
    expect(upscaled.find('[data-testid="quality-badge"]').text()).toContain('Verlustbehaftet');
    expect(upscaled.find('[data-testid="quality-badge"]').attributes('title')).toContain(
      'bessere Qualität',
    );
  });

  it('marks inconclusive results to be checked instead of a badge', () => {
    const suspicious = badge({ effective: null, status: 'suspicious' });

    expect(suspicious.find('[data-testid="quality-check"]').text()).toContain('Prüfen');
    expect(suspicious.find('[data-testid="quality-badge"]').exists()).toBe(false);
  });
});

const SUMMARY = 'summary';
const summary = (overrides: Record<string, number> = {}) => ({
  id: SUMMARY,
  key: [SUMMARY],
  unanalysed: 1200,
  genuine: 0,
  suspicious: 0,
  upscaled: 0,
  confirmed_genuine: 0,
  ...overrides,
});

async function settingsPage(start = () => json({ job_id: 'job-1' }, 202)) {
  const posted: unknown[] = [];
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role: 'editor' })),
      'POST /api/v1/quality-analysis': async (request) => {
        posted.push(await request.json());
        return start();
      },
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/settings', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await vi.waitFor(() => expect(subscription(socket)).toBeDefined());
  return { wrapper, socket, posted };
}

function subscription(socket: FakeSocket): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' && message.data.stream === 'quality_analysis.summary',
  );
}

describe('quality settings', () => {
  it('shows the files per status and follows deltas', async () => {
    const { wrapper, socket } = await settingsPage();
    const sub = subscription(socket)!.sub;
    socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: 1, counters: {} } });
    socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows: [summary()] } });
    await flushPromises();
    const count = (key: string) => wrapper.find(`[data-testid="quality-${key}"] .mono`).text();
    expect(count('unanalysed')).toBe('1.200');

    socket.receive({
      type: 'delta',
      sub,
      seq: 2,
      data: {
        op: 'upsert',
        id: SUMMARY,
        key: [SUMMARY],
        row: summary({ unanalysed: 1199, upscaled: 1 }),
        total: 1,
      },
    });
    await flushPromises();

    expect(count('unanalysed')).toBe('1.199');
    expect(count('upscaled')).toBe('1');
  });

  it('starts the analysis and reports a running one', async () => {
    const { wrapper, posted } = await settingsPage();
    await wrapper.find('[data-testid="quality-full"]').trigger('click');
    await wrapper.find('[data-testid="quality-start"]').trigger('click');
    await flushPromises();
    expect(posted).toEqual([{ full: true }]);
    expect(wrapper.find('[data-testid="quality-message"]').text()).toContain('läuft als Auftrag');

    const running = await settingsPage(() => json({ detail: 'analysis_running' }, 409));
    await running.wrapper.find('[data-testid="quality-start"]').trigger('click');
    await flushPromises();
    expect(running.wrapper.find('[data-testid="quality-message"]').text()).toContain(
      'läuft bereits',
    );
  });
});
