import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const side = (id: string, title: string) => ({
  recording_id: id,
  title,
  artist: 'Nordlicht',
  duration_ms: 200_000,
  format: 'flac',
  effective_quality: null,
});

const matchRow = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  key: [1, '2026-10-23T10:00:00+00:00', id],
  type: 'recording_match',
  subject_type: 'recording',
  subject_id: `rec-${id}`,
  origin: 'fuzzy_match',
  confidence: 'low',
  status: 'open',
  summary: {
    subject: 'Nordlicht - Eisfeld',
    current: 'Nordlicht - Eisfeld',
    proposed: 'Nordlicht - Eisfeld',
  },
  evidence: {
    subject: side(`rec-${id}`, 'Eisfeld'),
    other: side('rec-other', 'Eisfeld'),
    fingerprint_similarity: 0.41,
    mb_recording_id: null,
  },
  proposal: { into: 'rec-other' },
  note: null,
  created_at: '2026-10-23T10:00:00+00:00',
  decided_by: null,
  decided_by_name: null,
  decided_at: null,
  choices: [],
  applicable: true,
  ...overrides,
});

const qualityRow = () => ({
  ...matchRow('q'),
  type: 'quality_finding',
  subject_type: 'audio_hash',
  subject_id: 'c'.repeat(64),
  origin: 'quality_analysis',
  confidence: 'medium',
  summary: { subject: 'Nordlicht - Tauwetter', current: 'cd_lossless', proposed: 'lossy_low' },
  evidence: {
    audio_hash: 'c'.repeat(64),
    status: 'suspicious',
    finding: 'cutoff_without_encoder_match',
    values: { cutoff_hz: 18000 },
    declared_quality: 'cd_lossless',
    format: 'flac',
    sample_rate_hz: 44100,
    bit_depth: 16,
    bitrate_kbps: null,
    files: 1,
    recording: null,
  },
  proposal: { upscaled_quality: 'lossy_low' },
  choices: ['genuine', 'upscaled'],
});

async function reviewPage(
  role = 'editor',
  decision: (body: unknown) => Response = () =>
    json({ status: 'accepted', job_id: null, selected: 1 }),
) {
  const bodies: unknown[] = [];
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'POST /api/v1/review/decisions': async (request) => {
        const body = await request.json();
        bodies.push(body);
        return decision(body);
      },
      [`GET /api/v1/quality-analysis/${'c'.repeat(64)}/spectrogram.png`]: () =>
        new Response(new Uint8Array([137, 80, 78, 71]), {
          headers: { 'Content-Type': 'image/png' },
        }),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/review', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, bodies };
}

function listSubscriptions(socket: FakeSocket): Subscribe[] {
  return socket.sent.filter(
    (message): message is Subscribe =>
      message.type === 'subscribe' &&
      message.data.stream === 'review.items' &&
      message.data.end > 0,
  );
}

async function sendRows(
  socket: FakeSocket,
  rows: Record<string, unknown>[],
  counters: Record<string, number>,
) {
  await vi.waitFor(() => expect(listSubscriptions(socket).length).toBeGreaterThan(0));
  const subscriptions = listSubscriptions(socket);
  const { sub } = subscriptions[subscriptions.length - 1]!;
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: rows.length, counters } });
  socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  await flushPromises();
  return sub;
}

function navCount(socket: FakeSocket): Subscribe | undefined {
  return socket.sent.find(
    (message): message is Subscribe =>
      message.type === 'subscribe' &&
      message.data.stream === 'review.items' &&
      message.data.end === 0,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('review list', () => {
  it('shows counts, entries and the evidence of a fuzzy match', async () => {
    const { wrapper, socket, bodies } = await reviewPage();
    await sendRows(socket, [matchRow('a'), matchRow('b')], {
      'status.open': 2,
      'status.deferred': 1,
      'type.recording_match': 2,
    });

    expect(wrapper.find('[data-testid="review-total"]').text()).toContain('2 Einträge');
    const status = wrapper.find('[data-testid="review-filter-status"]');
    expect(status.text()).toContain('Zurückgestellt (1)');
    expect(wrapper.find('[data-testid="review-row-rec-a"]').text()).toContain('Niedrig');

    await wrapper.find('[data-testid="review-row-rec-a"] button').trigger('click');
    const detail = wrapper.find('[data-testid="review-detail"]');
    expect(detail.text()).toContain('Gleiche Aufnahme?');
    expect(wrapper.find('[data-testid="review-similarity"]').text()).toContain('41');
    await wrapper.find('[data-testid="review-accept"]').trigger('click');
    await vi.waitFor(() => expect(bodies).toHaveLength(1));
    await flushPromises();

    expect(bodies[0]).toEqual({ ids: ['a'], decision: 'accept', choice: null });
    expect(wrapper.find('[data-testid="review-message"]').text()).toContain('Angenommen');
    expect(navCount(socket)?.data.params).toEqual({ status: 'open' });
  });

  it('decides quality findings with one of two answers and shows the spectrogram', async () => {
    vi.stubGlobal(
      'URL',
      Object.assign(URL, {
        createObjectURL: () => 'blob:spectrogram',
        revokeObjectURL: () => undefined,
      }),
    );
    const { wrapper, socket, bodies } = await reviewPage();
    await sendRows(socket, [qualityRow()], { 'status.open': 1 });

    await wrapper.find(`[data-testid="review-row-${'c'.repeat(64)}"] button`).trigger('click');
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="spectrogram"] img').exists()).toBe(true),
    );
    expect(wrapper.find('[data-testid="review-proposed"]').text()).toContain('Verlustbehaftet');
    expect(wrapper.find('[data-testid="review-accept"]').exists()).toBe(false);
    await wrapper.find('[data-testid="review-choice-genuine"]').trigger('click');
    await vi.waitFor(() => expect(bodies).toHaveLength(1));

    expect(bodies[0]).toEqual({ ids: ['q'], decision: 'accept', choice: 'genuine' });
  });

  it('rejects a multi-selection and runs a rule after confirmation', async () => {
    const { wrapper, socket, bodies } = await reviewPage('admin', () =>
      json({ status: null, job_id: 'job-1', selected: 2 }),
    );
    await sendRows(socket, [matchRow('a'), matchRow('b'), matchRow('c')], { 'status.open': 3 });

    await wrapper.find('[data-testid="review-row-rec-a"] input').setValue(true);
    await wrapper.find('[data-testid="review-row-rec-c"] input').setValue(true);
    expect(wrapper.find('[data-testid="review-bar"]').text()).toContain('2 ausgewählt');
    await wrapper.find('[data-testid="review-bar-reject"]').trigger('click');
    await vi.waitFor(() => expect(bodies).toHaveLength(1));
    await flushPromises();
    expect(bodies[0]).toEqual({ ids: ['a', 'c'], decision: 'reject', choice: null });
    expect(wrapper.find('[data-testid="review-message"]').text()).toContain('Hintergrund');
    expect(wrapper.find('[data-testid="review-bar"]').exists()).toBe(false);

    await wrapper.find('[data-testid="review-reject-all"]').trigger('click');
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="review-rule-confirm"]')).not.toBeNull(),
    );
    expect(bodies).toHaveLength(1); // nothing before the confirmation
    (document.body.querySelector('[data-testid="review-rule-confirm"]') as HTMLElement).click();
    await vi.waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual({
      rule: { status: 'open', type: null, origin: null, confidence: null },
      decision: 'reject',
      choice: null,
    });
  });

  it('subscribes again with a new filter', async () => {
    const { wrapper, socket } = await reviewPage();
    await sendRows(socket, [matchRow('a')], { 'status.open': 1 });

    await wrapper.find('[data-testid="review-filter-type"]').setValue('quality_finding');
    await vi.waitFor(() => expect(listSubscriptions(socket)).toHaveLength(2));

    expect(listSubscriptions(socket)[1]!.data.params).toEqual({
      status: 'open',
      type: 'quality_finding',
    });
  });

  it('is offered to editors and admins only', async () => {
    const { wrapper, socket } = await reviewPage('listener');

    expect(wrapper.router.currentRoute.value.name).not.toBe('review');
    expect(wrapper.text()).not.toContain('Prüfliste');
    expect(navCount(socket)).toBeUndefined();
  });
});
