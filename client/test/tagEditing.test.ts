import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const release = {
  id: 'polarnacht',
  key: ['polarnacht'],
  title: 'Polarnacht',
  album_artist: 'Nordlicht',
  album_artist_id: 'nordlicht',
  edition: null,
  year: 2024,
  disc_count: 1,
  track_count: 4,
};

const track = (id: string, number: number) => ({
  id,
  key: [1, number, id],
  title: `Track ${id}`,
  artist: 'Nordlicht',
  album: 'Polarnacht',
  album_artist: 'Nordlicht',
  release_id: 'polarnacht',
  recording_id: `recording-${id}`,
  disc_number: 1,
  track_number: number,
  duration_ms: 252_000,
  format: 'flac',
  sample_rate_hz: 44_100,
  bit_depth: 16,
  bitrate_kbps: null,
  effective_quality: null,
  quality_status: null,
});

const mixed = { value: null, mixed: true };
const VALUES = {
  items: 2,
  fields: {
    recording: {
      title: mixed,
      artist: { value: 'Nordlicht', mixed: false },
      genres: { value: ['Marsch'], mixed: false },
      composers: { value: [], mixed: false },
      isrc: mixed,
      mb_recording_id: { value: null, mixed: false },
    },
    release: {
      title: { value: 'Polarnacht', mixed: false },
      album_artist: { value: 'Nordlicht', mixed: false },
      year: { value: 2024, mixed: false },
      label: { value: null, mixed: false },
    },
    track: {
      album: { value: 'Polarnacht', mixed: false },
      album_artist: { value: 'Nordlicht', mixed: false },
      track_number: mixed,
      disc_number: { value: 1, mixed: false },
      context_title: { value: null, mixed: false },
      context_artist: { value: null, mixed: false },
    },
  },
};

async function page(
  path: string,
  role = 'editor',
  edited = () => json({ items: 2, changed: 2, change_set_id: 'set-1', job_id: null }),
) {
  const bodies: { edits: unknown[]; values: unknown[]; undo: unknown[] } = {
    edits: [],
    values: [],
    undo: [],
  };
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'POST /api/v1/tagging/values': async (request) => {
        bodies.values.push(await request.json());
        return json(VALUES);
      },
      'POST /api/v1/tagging/edits': async (request) => {
        bodies.edits.push(await request.json());
        return edited();
      },
      'POST /api/v1/tagging/changes/set-1/undo': () => {
        bodies.undo.push('set-1');
        return json({ change_set_id: 'set-2', job_id: 'job-1' }, 202);
      },
      'GET /api/v1/metadata-lookup/status': () =>
        json({
          mirror_configured: false,
          mirror_status: null,
          queued_requests: 0,
          estimated_seconds: 0,
          mirror_recommended: false,
        }),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path, guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, bodies };
}

async function serve(
  socket: FakeSocket,
  stream: string,
  rows: Record<string, unknown>[],
  counters = {},
) {
  const find = () =>
    socket.sent.filter(
      (message): message is Subscribe =>
        message.type === 'subscribe' && message.data.stream === stream && message.data.end > 0,
    );
  await vi.waitFor(() => expect(find().length).toBeGreaterThan(0));
  const { sub } = find().at(-1)!;
  socket.receive({ type: 'snapshot_meta', sub, seq: 1, data: { total: rows.length, counters } });
  if (rows.length) socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  await flushPromises();
}

const inBody = (testId: string) =>
  document.body.querySelector<HTMLInputElement>(`[data-testid="${testId}"]`);

async function albumInEditMode(role = 'editor', edited?: () => Response) {
  const result = await page('/local/releases/polarnacht', role, edited);
  await serve(result.socket, 'library.release', [release]);
  await serve(result.socket, 'library.release.tracks', [
    track('a', 1),
    track('b', 2),
    track('c', 3),
    track('d', 4),
  ]);
  await result.wrapper.find('[data-testid="mode-edit"]').trigger('click');
  return result;
}

describe('tag editing', () => {
  it('selects tracks, shows mixed values and sends only edited fields', async () => {
    const { wrapper, bodies } = await albumInEditMode();

    await wrapper.find('[data-testid="select-a"]').trigger('click');
    await wrapper.find('[data-testid="select-c"]').trigger('click', { shiftKey: true });
    expect(wrapper.find('[data-testid="edit-count"]').text()).toContain('3 ausgewählt');
    await wrapper.find('[data-testid="select-b"]').trigger('click');
    expect(wrapper.find('[data-testid="edit-count"]').text()).toContain('2 ausgewählt');

    await wrapper.find('[data-testid="edit-tags"]').trigger('click');
    await vi.waitFor(() => expect(inBody('tag-field-genres')).not.toBeNull());
    await vi.waitFor(() => expect(inBody('tag-field-genres')!.value).toBe('Marsch'));
    expect(bodies.values).toEqual([{ ids: ['a', 'c'] }]);
    expect(inBody('tag-field-title')!.placeholder).toBe('verschiedene Werte');
    expect(inBody('tag-field-track_number')).toBeNull(); // positions only for one track
    expect(inBody('tag-editor-count')?.textContent).toContain('2 Titel');

    const genres = inBody('tag-field-genres')!;
    genres.value = 'Marsch, Polka';
    genres.dispatchEvent(new Event('input'));
    const year = inBody('tag-field-year')!;
    year.value = '1985';
    year.dispatchEvent(new Event('input'));
    await flushPromises();
    inBody('tag-editor-apply')!.click();
    await vi.waitFor(() => expect(bodies.edits).toHaveLength(1));
    await flushPromises();

    expect(bodies.edits[0]).toEqual({
      ids: ['a', 'c'],
      fields: { recording: { genres: ['Marsch', 'Polka'] }, release: { year: 1985 } },
      preview: false,
    });
    expect(wrapper.find('[data-testid="edit-message"]').text()).toContain('2 Einträge geändert');
  });

  it('selects the whole list as a rule and reports a bulk job', async () => {
    const { wrapper, bodies } = await albumInEditMode('admin', () =>
      json({ items: 4, changed: null, change_set_id: 'set-1', job_id: 'job-1' }),
    );

    await wrapper.find('[data-testid="select-all"]').trigger('click');
    expect(wrapper.find('[data-testid="edit-count"]').text()).toContain('4 ausgewählt');
    await wrapper.find('[data-testid="edit-tags"]').trigger('click');
    await vi.waitFor(() => expect(inBody('tag-field-label')).not.toBeNull());
    const label = inBody('tag-field-label')!;
    label.value = 'Eis';
    label.dispatchEvent(new Event('input'));
    await flushPromises();
    inBody('tag-editor-apply')!.click();
    await vi.waitFor(() => expect(bodies.edits).toHaveLength(1));
    await flushPromises();

    expect(bodies.edits[0]).toEqual({
      rule: { list: 'release_tracks', release_id: 'polarnacht' },
      fields: { release: { label: 'Eis' } },
      preview: false,
    });
    expect(wrapper.find('[data-testid="edit-message"]').text()).toContain('Hintergrund');
  });

  it('edits the album itself from its page', async () => {
    const { wrapper, bodies } = await albumInEditMode();

    await wrapper.find('[data-testid="edit-release"]').trigger('click');
    await vi.waitFor(() => expect(inBody('tag-field-title')!.value).toBe('Polarnacht'));
    expect(inBody('tag-field-genres')).toBeNull();
    const title = inBody('tag-field-title')!;
    title.value = 'Polarnacht (Deluxe)';
    title.dispatchEvent(new Event('input'));
    await flushPromises();
    inBody('tag-editor-apply')!.click();
    await vi.waitFor(() => expect(bodies.edits).toHaveLength(1));

    expect(bodies.edits[0]).toEqual({
      rule: { list: 'release_tracks', release_id: 'polarnacht' },
      fields: { release: { title: 'Polarnacht (Deluxe)' } },
      preview: false,
    });
  });

  it('is not offered to listeners', async () => {
    const { wrapper, socket } = await page('/local/releases/polarnacht', 'listener');
    await serve(socket, 'library.release', [release]);

    expect(wrapper.find('[data-testid="mode-edit"]').exists()).toBe(false);
  });

  it('shows the change history with undo and pending writes', async () => {
    const { wrapper, socket, bodies } = await page('/settings');
    await serve(
      socket,
      'tagging.changes',
      [
        {
          id: 'set-1',
          key: ['2026-10-24T10:00:00+00:00', 'set-1'],
          kind: 'edit',
          user_name: 'Andrea',
          summary: { fields: { recording: { genres: ['Marsch'] } } },
          items: 12,
          changed: 12,
          created_at: '2026-10-24T10:00:00+00:00',
          job_id: null,
          undo_of: null,
          undone_by: null,
          undoable: true,
        },
      ],
      { pending_writes: 3, failed_writes: 0 },
    );

    const row = wrapper.find('[data-testid="change-set-1"]');
    expect(row.text()).toContain('Genre: Marsch');
    expect(row.text()).toContain('Andrea');
    expect(row.text()).toContain('12 von 12 geändert');
    expect(wrapper.find('[data-testid="tag-writes"]').text()).toContain('3 Dateien warten');
    await wrapper.find('[data-testid="undo-set-1"]').trigger('click');
    await vi.waitFor(() => expect(bodies.undo).toEqual(['set-1']));
    await flushPromises();
    expect(wrapper.find('[data-testid="history-message"]').text()).toContain('rückgängig');
  });
});
