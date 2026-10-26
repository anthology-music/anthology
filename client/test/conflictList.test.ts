import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const conflict = (id: string, field = 'title') => ({
  id,
  key: [1, '2026-10-25T10:00:00+00:00', id],
  type: 'tag_conflict',
  subject_type: 'recording',
  subject_id: `recording-${id}`,
  origin: 'musicbrainz',
  confidence: 'medium',
  status: 'open',
  summary: { subject: `Nordlicht - ${id}`, current: id, proposed: `${id} (Remaster)` },
  evidence: { level: 'recording', field, current: id, source: 'musicbrainz' },
  proposal: { field, value: `${id} (Remaster)` },
  note: null,
  created_at: '2026-10-25T10:00:00+00:00',
  decided_by: null,
  decided_by_name: null,
  decided_at: null,
  choices: [],
  applicable: true,
});

async function conflictsPage(role = 'editor') {
  const bodies: unknown[] = [];
  const groupQueries: string[] = [];
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'GET /api/v1/tagging/conflicts/groups': (request) => {
        groupQueries.push(new URL(request.url).searchParams.get('by') ?? '');
        return json([
          { value: 'polarnacht', label: 'Nordlicht - Polarnacht', count: 2 },
          { value: 'splitter', label: 'Glas - Splitter', count: 1 },
        ]);
      },
      'POST /api/v1/review/decisions': async (request) => {
        const body: unknown = await request.json();
        bodies.push(body);
        return json({ status: 'accepted', job_id: null, selected: 1 });
      },
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path: '/conflicts', guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, bodies, groupQueries };
}

function lists(socket: FakeSocket): Subscribe[] {
  return socket.sent.filter(
    (message): message is Subscribe =>
      message.type === 'subscribe' &&
      message.data.stream === 'tagging.conflicts' &&
      message.data.end > 0,
  );
}

async function serve(socket: FakeSocket, rows: Record<string, unknown>[]) {
  await vi.waitFor(() => expect(lists(socket).length).toBeGreaterThan(0));
  const { sub } = lists(socket).at(-1)!;
  socket.receive({
    type: 'snapshot_meta',
    sub,
    seq: 1,
    data: { total: rows.length, counters: {} },
  });
  socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  await flushPromises();
}

describe('conflict list', () => {
  it('shows groups and conflicts and decides one entry', async () => {
    const { wrapper, socket, bodies, groupQueries } = await conflictsPage();
    await serve(socket, [conflict('a'), conflict('b', 'genres')]);
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="group-polarnacht"]').exists()).toBe(true),
    );

    expect(groupQueries[0]).toBe('release');
    expect(wrapper.find('[data-testid="group-polarnacht"]').text()).toContain('2');
    expect(wrapper.find('[data-testid="conflicts-total"]').text()).toContain('2 Konflikte');
    const row = wrapper.find('[data-testid="conflict-a"]');
    expect(row.text()).toContain('Nordlicht - a · Titel');
    expect(row.text()).toMatch(/a\s*→\s*a \(Remaster\)/);
    expect(wrapper.find('[data-testid="conflict-b"]').text()).toContain('Genre');
    await wrapper.find('[data-testid="conflict-accept-a"]').trigger('click');
    await vi.waitFor(() => expect(bodies).toHaveLength(1));

    expect(bodies[0]).toEqual({ ids: ['a'], decision: 'accept', choice: null });
  });

  it('filters by a group and decides the whole group after confirmation', async () => {
    const { wrapper, socket, bodies } = await conflictsPage();
    await serve(socket, [conflict('a'), conflict('b'), conflict('c')]);
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="group-polarnacht"]').exists()).toBe(true),
    );

    await wrapper.find('[data-testid="group-polarnacht"]').trigger('click');
    await vi.waitFor(() => expect(lists(socket)).toHaveLength(2));
    expect(lists(socket)[1]!.data.params).toEqual({ status: 'open', release_id: 'polarnacht' });
    await serve(socket, [conflict('a'), conflict('b')]);
    await wrapper.find('[data-testid="conflicts-accept-group"]').trigger('click');
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="conflicts-confirm"]')).not.toBeNull(),
    );
    expect(bodies).toEqual([]);
    (document.body.querySelector('[data-testid="conflicts-confirm"]') as HTMLElement).click();
    await vi.waitFor(() => expect(bodies).toHaveLength(1));

    expect(bodies[0]).toEqual({
      rule: { status: 'open', type: 'tag_conflict', release_id: 'polarnacht' },
      decision: 'accept',
      choice: null,
    });
  });

  it('keeps several selected conflicts at once', async () => {
    const { wrapper, socket, bodies } = await conflictsPage();
    await serve(socket, [conflict('a'), conflict('b'), conflict('c')]);

    await wrapper.find('[data-testid="conflict-a"] input').setValue(true);
    await wrapper.find('[data-testid="conflict-c"] input').setValue(true);
    expect(wrapper.find('[data-testid="conflicts-bar"]').text()).toContain('2 ausgewählt');
    await wrapper.find('[data-testid="conflicts-reject-selected"]').trigger('click');
    await vi.waitFor(() => expect(bodies).toHaveLength(1));

    expect(bodies[0]).toEqual({ ids: ['a', 'c'], decision: 'reject', choice: null });
  });

  it('is offered to editors and admins only', async () => {
    const { wrapper, socket } = await conflictsPage('listener');

    expect(wrapper.router.currentRoute.value.name).not.toBe('conflicts');
    expect(wrapper.text()).not.toContain('Konflikte');
    expect(lists(socket)).toEqual([]);
  });
});
