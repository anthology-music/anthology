import type { ClientMessage } from '@anthology/api-types';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from '@/App.vue';

import { json, tokens } from './fakeServer';
import type { FakeSocket } from './fakeSocket';
import { welcome } from './fakeSocket';
import { fakeServices, mountWithApp } from './mount';

type Subscribe = Extract<ClientMessage, { type: 'subscribe' }>;

const release = (id: string, cover: string | null) => ({
  id,
  key: [id],
  title: `Album ${id}`,
  album_artist: 'Nordlicht',
  album_artist_id: 'nordlicht',
  edition: null,
  year: 2024,
  disc_count: 1,
  track_count: 3,
  cover,
});

const GRANT = {
  prefix: '/api/v1/media/images',
  params: { u: 'user', d: 'device', exp: '1893456000', sig: 'signed' },
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
};

interface Call {
  method: string;
  path: string;
  type: string | null;
  size: number;
}

async function setup(path: string, role = 'admin', images: object[] = []) {
  const calls: Call[] = [];
  const record = (answer: (request: Request) => Response) => async (request: Request) => {
    const body = request.method === 'GET' ? null : await request.arrayBuffer();
    calls.push({
      method: request.method,
      path: new URL(request.url).pathname,
      type: request.headers.get('content-type'),
      size: body?.byteLength ?? 0,
    });
    return answer(request);
  };
  let gallery = images;
  const services = fakeServices(
    {
      'POST /api/v1/auth/refresh': () => json(tokens({ role })),
      'POST /api/v1/covers/grant': record(() => json(GRANT)),
      'PUT /api/v1/releases/a/cover': record(() =>
        json({ image_id: 'new', sha256: 'x', changed: true }),
      ),
      'DELETE /api/v1/releases/a/cover': record(() => new Response(null, { status: 204 })),
      'GET /api/v1/releases/a/images': record(() => json(gallery)),
      'POST /api/v1/releases/a/images': record(() => {
        gallery = [...gallery, { id: 'g9', kind: 'booklet', position: 9, image_id: 'img9' }];
        return json(gallery, 201);
      }),
      'DELETE /api/v1/releases/a/images/g1': record(() => new Response(null, { status: 204 })),
    },
    { 'anthology.refreshToken': 'device-1.stored' },
  );
  const wrapper = await mountWithApp(App, { path, guard: true });
  const socket = services.sockets.latest();
  socket.open();
  await vi.waitFor(() => expect(socket.last('hello')).toBeDefined());
  socket.receive(welcome());
  await flushPromises();
  return { wrapper, socket, calls };
}

async function serve(socket: FakeSocket, stream: string, rows: Record<string, unknown>[]) {
  const matching = () =>
    socket.sent.filter(
      (message): message is Subscribe =>
        message.type === 'subscribe' && message.data.stream === stream && message.data.end !== 0,
    );
  await vi.waitFor(() => expect(matching().length).toBeGreaterThan(0));
  const { sub } = matching().at(-1)!;
  socket.receive({
    type: 'snapshot_meta',
    sub,
    seq: 1,
    data: { total: rows.length, counters: {} },
  });
  socket.receive({ type: 'chunk', sub, data: { chunk: 0, start: 0, rows } });
  await flushPromises();
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('covers', () => {
  it('shows thumbnails with the device grant, and a placeholder without a cover', async () => {
    const { wrapper, socket, calls } = await setup('/local/albums');
    await serve(socket, 'library.releases', [release('a', 'img1'), release('b', null)]);

    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="album-cover-a"] img').exists()).toBe(true),
    );
    const src = wrapper.find('[data-testid="album-cover-a"] img').attributes('src')!;
    const placeholder = wrapper.find('[data-testid="album-cover-b"] [data-cover="placeholder"]');

    expect(src).toBe('/api/v1/media/images/img1/64?u=user&d=device&exp=1893456000&sig=signed');
    expect(wrapper.find('[data-testid="album-cover-a"] img').attributes('loading')).toBe('lazy');
    expect(placeholder.exists()).toBe(true);
    expect(placeholder.attributes('aria-label')).toBe('Cover von Album b (Nordlicht)');
    // One grant for every image of the list.
    expect(calls.filter((call) => call.path === '/api/v1/covers/grant')).toHaveLength(1);
  });

  it('uploads and removes the cover of an album', async () => {
    const { wrapper, socket, calls } = await setup('/local/releases/a');
    await serve(socket, 'library.release', [release('a', 'img1')]);

    const file = new File([new Uint8Array([137, 80, 78, 71])], 'cover.png', { type: 'image/png' });
    const input = wrapper.find('[data-testid="cover-upload"]');
    Object.defineProperty(input.element, 'files', { value: [file] });
    await input.trigger('change');
    await wrapper.find('[data-testid="cover-remove"]').trigger('click');

    await vi.waitFor(() => {
      const cover = calls.filter((call) => call.path === '/api/v1/releases/a/cover');
      // Requests overlap: compare without their order.
      expect(cover.map((call) => [call.method, call.type, call.size]).sort()).toEqual([
        ['DELETE', null, 0],
        ['PUT', 'image/png', 4],
      ]);
    });
    expect(wrapper.find('[data-testid="album-cover"] img').attributes('src')).toContain(
      '/img1/256?',
    );
  });

  it('opens the gallery on demand and lets editors change it', async () => {
    const images = [
      { id: 'g1', kind: 'back', position: 1, image_id: 'img2' },
      { id: 'g2', kind: 'booklet', position: 2, image_id: null },
    ];
    const { wrapper, socket, calls } = await setup('/local/releases/a', 'admin', images);
    await serve(socket, 'library.release', [release('a', null)]);
    expect(calls.some((call) => call.path === '/api/v1/releases/a/images')).toBe(false);

    await wrapper.find('[data-testid="open-gallery"]').trigger('click');
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="gallery-image-1"]')).not.toBeNull(),
    );
    const first = document.body.querySelector('[data-testid="gallery-image-0"]')!;
    expect(first.textContent).toContain('Rückseite');
    expect(first.querySelector('img')!.getAttribute('src')).toContain('/img2/256?');
    const file = new File([new Uint8Array([1, 2, 3])], 'booklet.jpg', { type: 'image/jpeg' });
    const input = document.body.querySelector<HTMLInputElement>('[data-testid="gallery-file"]')!;
    Object.defineProperty(input, 'files', { value: [file] });
    input.dispatchEvent(new Event('change'));
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="gallery-image-2"]')).not.toBeNull(),
    );
    document.body.querySelector<HTMLElement>('[data-testid="gallery-remove-0"]')!.click();

    await vi.waitFor(() =>
      expect(
        calls
          .filter((call) => call.path.startsWith('/api/v1/releases/a/images'))
          .map((call) => `${call.method} ${call.path}`),
      ).toEqual([
        'GET /api/v1/releases/a/images',
        'POST /api/v1/releases/a/images',
        'DELETE /api/v1/releases/a/images/g1',
      ]),
    );
  });

  it('shows no upload to listeners', async () => {
    const { wrapper, socket } = await setup('/local/releases/a', 'listener');
    await serve(socket, 'library.release', [release('a', 'img1')]);

    expect(wrapper.find('[data-testid="release-title"]').text()).toBe('Album a');
    expect(wrapper.find('[data-testid="cover-upload"]').exists()).toBe(false);
  });
});
