import { describe, expect, it } from 'vitest';

import { formatDuration, formatLabel, trackNumber } from '@/features/library/format';

const file = (overrides: Partial<Parameters<typeof formatLabel>[0]> = {}) => ({
  format: 'flac' as const,
  sample_rate_hz: 96_000,
  bit_depth: 24,
  bitrate_kbps: null,
  ...overrides,
});

describe('library formatting', () => {
  it('labels lossless files with bit depth and sample rate in kHz', () => {
    expect(formatLabel(file())).toBe('FLAC 24/96');
    expect(formatLabel(file({ format: 'wav', sample_rate_hz: 44_100, bit_depth: 16 }))).toBe(
      'WAV 16/44.1',
    );
    expect(formatLabel(file({ bit_depth: null, sample_rate_hz: 48_000 }))).toBe('FLAC 48');
  });

  it('labels lossy files with the bitrate', () => {
    const mp3 = file({ format: 'mp3', sample_rate_hz: 44_100, bit_depth: null });
    expect(formatLabel({ ...mp3, bitrate_kbps: 320 })).toBe('MP3 320');
    expect(formatLabel(mp3)).toBe('MP3');
  });

  it('shows nothing without a file', () => {
    expect(formatLabel(file({ format: null }))).toBe('');
  });

  it('formats durations', () => {
    expect(formatDuration(252_000)).toBe('4:12');
    expect(formatDuration(59_600)).toBe('1:00');
    expect(formatDuration(3_725_000)).toBe('1:02:05');
  });

  it('prefixes the disc on multi-disc releases only', () => {
    expect(trackNumber(1, 5, 1)).toBe('05');
    expect(trackNumber(2, 5, 2)).toBe('2-05');
    expect(trackNumber(1, 12, 3)).toBe('1-12');
  });
});
