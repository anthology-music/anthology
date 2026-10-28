import { describe, expect, it } from 'vitest';

import TrackRow from '@/features/library/components/TrackRow.vue';

import { fakeServices, mountWithApp } from './mount';

const track = (overrides: Record<string, unknown> = {}) => ({
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
  ...overrides,
});

describe('track source', () => {
  it('shows where a downloaded track comes from and when it was retrieved', async () => {
    fakeServices();
    const wrapper = await mountWithApp(TrackRow, {
      props: {
        track: track({ source: 'Tidal', source_short: 'TD', retrieved_at: '2026-10-28T10:00:00Z' }),
        context: 'release',
      },
    });

    const badge = wrapper.find('[data-testid="track-source"]');
    expect(badge.text()).toBe('TD');
    expect(badge.attributes('title')).toContain('Tidal, abgerufen am');
    expect(badge.attributes('title')).toContain('2026');
  });

  it('shows nothing for imported tracks', async () => {
    fakeServices();
    const wrapper = await mountWithApp(TrackRow, { props: { track: track(), context: 'release' } });

    expect(wrapper.find('[data-testid="track-source"]').exists()).toBe(false);
  });
});
