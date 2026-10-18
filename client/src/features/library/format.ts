import type { AudioFormat, LibraryTrackRow } from '@anthology/api-types';

const LOSSLESS: ReadonlySet<AudioFormat> = new Set(['flac', 'wav', 'aiff', 'alac']);

/** `4:12`, or `1:02:05` from one hour on. */
export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}`
    : `${minutes}:${seconds}`;
}

/**
 * The file's format as technical information (spec: library, Format label):
 * `FLAC 24/96` for lossless formats, `MP3 320` for lossy ones. Never a quality rating.
 */
export function formatLabel(
  row: Pick<LibraryTrackRow, 'format' | 'sample_rate_hz' | 'bit_depth' | 'bitrate_kbps'>,
): string {
  if (!row.format) return '';
  const name = row.format.toUpperCase();
  if (LOSSLESS.has(row.format)) {
    if (!row.sample_rate_hz) return name;
    const khz = String(Math.round(row.sample_rate_hz / 100) / 10);
    return row.bit_depth ? `${name} ${row.bit_depth}/${khz}` : `${name} ${khz}`;
  }
  return row.bitrate_kbps ? `${name} ${row.bitrate_kbps}` : name;
}

/** `05`, or `2-05` on releases with more than one disc. */
export function trackNumber(disc: number, track: number, discCount: number): string {
  const number = String(track).padStart(2, '0');
  return discCount > 1 ? `${disc}-${number}` : number;
}
