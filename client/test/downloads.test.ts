import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import DownloadNotice from '@/features/library/components/DownloadNotice.vue';
import { setSaveLink, useDownloadStore } from '@/features/library/downloads';
import PlayableTrackRow from '@/features/playback/components/PlayableTrackRow.vue';

import { json } from './fakeServer';
import { fakeServices, mountWithApp } from './mount';

const track = {
  id: 't1',
  key: [],
  title: 'Treibeis',
  artist: 'Nordlicht',
  album: 'Polarnacht',
  album_artist: 'Nordlicht',
  release_id: 'r1',
  recording_id: 'rec1',
  disc_number: 1,
  track_number: 2,
  duration_ms: 9_000,
  format: 'flac',
  sample_rate_hz: 44_100,
  bit_depth: 16,
  bitrate_kbps: null,
  effective_quality: null,
  quality_status: null,
  source: null,
  source_short: null,
  retrieved_at: null,
};

const answer = (tagged: boolean, fileName: string) =>
  json({
    url: '/api/v1/media/downloads/x?sig=1',
    expires_at: '2026-10-28T12:00:00Z',
    file_name: fileName,
    tagged,
    notice: tagged ? null : 'tagger_unavailable',
  });

afterEach(() => {
  document.body.innerHTML = '';
});

describe('downloads', () => {
  it('downloads a track from its menu with the tags of its context', async () => {
    const saved: string[][] = [];
    setSaveLink((url, name) => saved.push([url, name]));
    const { server } = fakeServices({
      'POST /api/v1/library/tracks/t1/download': () => answer(true, '02 Treibeis.flac'),
    });
    const wrapper = await mountWithApp(PlayableTrackRow, {
      props: { track, context: 'release' },
    });

    await wrapper.find('[data-testid="more-t1"]').trigger('click');
    await vi.waitFor(() =>
      expect(document.body.querySelector('[data-testid="download-t1"]')).not.toBeNull(),
    );
    document.body.querySelector<HTMLElement>('[data-testid="download-t1"]')!.click();
    await vi.waitFor(() => expect(saved).toHaveLength(1));

    expect(server.calls).toContain('POST /api/v1/library/tracks/t1/download');
    expect(saved[0]).toEqual(['/api/v1/media/downloads/x?sig=1', '02 Treibeis.flac']);
    expect(useDownloadStore().notice).toBeNull();
  });

  it('says when an album comes without context tags, until dismissed', async () => {
    const saved: string[][] = [];
    setSaveLink((url, name) => saved.push([url, name]));
    fakeServices({
      'POST /api/v1/library/releases/r1/download': () =>
        answer(false, 'Nordlicht - Polarnacht.zip'),
    });
    const wrapper = await mountWithApp(DownloadNotice);

    await useDownloadStore().downloadRelease('r1');
    await flushPromises();

    expect(saved[0]![1]).toBe('Nordlicht - Polarnacht.zip');
    expect(wrapper.find('[data-testid="download-notice"]').text()).toContain(
      'Ohne Kontext-Tags geladen',
    );
    await wrapper.find('[data-testid="download-notice-close"]').trigger('click');
    expect(wrapper.find('[data-testid="download-notice"]').exists()).toBe(false);
  });

  it('reports a download that could not start', async () => {
    const saved: string[][] = [];
    setSaveLink((url, name) => saved.push([url, name]));
    fakeServices({
      'POST /api/v1/library/tracks/t1/download': () => json({ detail: 'unknown_track' }, 404),
    });
    const wrapper = await mountWithApp(DownloadNotice);

    await useDownloadStore().downloadTrack('t1');
    await flushPromises();

    expect(saved).toEqual([]);
    expect(wrapper.find('[data-testid="download-notice"]').text()).toContain(
      'konnte nicht gestartet werden',
    );
  });
});
