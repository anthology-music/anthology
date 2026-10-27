import type { AudioLike } from './audio';

/** MIME types of the original formats (spec: playback, Formats the device cannot play). */
const TYPES: Record<string, string> = {
  flac: 'audio/flac',
  mp3: 'audio/mpeg',
  aac: 'audio/mp4; codecs="mp4a.40.2"',
  alac: 'audio/mp4; codecs="alac"',
  opus: 'audio/ogg; codecs="opus"',
  vorbis: 'audio/ogg; codecs="vorbis"',
  wav: 'audio/wav',
  aiff: 'audio/aiff',
};

/** The original formats this device can play; kept as a list so that it can be sent to the
 * server later (change playable-delivery-format). */
export function playableFormats(audio: AudioLike): Set<string> {
  return new Set(
    Object.entries(TYPES)
      .filter(([, type]) => audio.canPlayType(type) !== '')
      .map(([format]) => format),
  );
}
