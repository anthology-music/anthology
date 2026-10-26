import type { Schemas } from '@anthology/api-types';

export type SearchToken = Schemas['SearchToken'];
export type ItemType = 'artist' | 'release' | 'track';

/** Result streams per item type (spec: search, one list per type with the library's rows). */
export const STREAMS: Record<ItemType, string> = {
  artist: 'search.artists',
  release: 'search.releases',
  track: 'search.tracks',
};

/** Fields offered when adding a filter chip (docs/architecture/search-syntax.md). */
export const FILTER_FIELDS = [
  'artist',
  'album',
  'composer',
  'genre',
  'year',
  'format',
  'quality',
  'type',
] as const;

/** Lists end at this many results; larger counts are shown as "10,000+". */
export const CAP = 10_000;

/** The search context: one album or one artist, with its name for the chip. */
export interface SearchContext {
  release_id?: string | undefined;
  artist_id?: string | undefined;
  label?: string | undefined;
}

/** The text without one token (removing a chip removes its token). */
export function removeToken(text: string, token: SearchToken): string {
  return `${text.slice(0, token.start)} ${text.slice(token.end)}`.replace(/\s+/g, ' ').trim();
}

/** The text with a filter token appended (adding a chip appends its token). */
export function appendFilter(text: string, field: string, value: string): string {
  const trimmed = value.trim().replaceAll('"', '');
  if (!trimmed) return text;
  const token = /\s/.test(trimmed) ? `${field}:"${trimmed}"` : `${field}:${trimmed}`;
  return `${text.trim()} ${token}`.trim();
}

/** The parameters of a result subscription. */
export function searchParams(q: string, context: SearchContext): Record<string, unknown> {
  return {
    q,
    ...(context.release_id ? { release_id: context.release_id } : {}),
    ...(context.artist_id ? { artist_id: context.artist_id } : {}),
  };
}

/** The bulk-edit rule of all track results (spec: search, Results as selection rule). */
export function searchRule(q: string, context: SearchContext): Schemas['EditRule'] {
  return {
    list: 'search',
    q,
    release_id: context.release_id ?? null,
    artist_id: context.artist_id ?? null,
  };
}
