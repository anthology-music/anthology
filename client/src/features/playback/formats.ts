import { type AudioLike, createAudio } from './audio';

/** MIME types of the original formats (spec: transcoding, Format-aware delivery). */
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
// Browsers answer "maybe" for these types without codecs, although they play them.
const MAYBE_IS_ENOUGH = new Set(['flac', 'mp3', 'wav']);

/**
 * The audio formats this device can play, sent to the server in `hello`, which decides
 * between original and transcode. Only "probably" counts, except for the formats that
 * browsers report as "maybe".
 */
export function playableFormats(audio: AudioLike = createAudio()): string[] {
  return Object.entries(TYPES)
    .filter(([format, type]) => {
      const answer = audio.canPlayType(type);
      return answer === 'probably' || (answer === 'maybe' && MAYBE_IS_ENOUGH.has(format));
    })
    .map(([format]) => format)
    .sort();
}
