import type { Schemas } from '@anthology/api-types';

import { getServices } from '@/services';

export type Visibility = Schemas['PlaylistIn']['visibility'];
export type FavoriteTarget = 'recording' | 'release' | 'artist';
export type PlaylistProblem =
  | 'forbidden'
  | 'changed_since'
  | 'unknown_playlist'
  | 'playlist_too_large'
  | 'invalid_file'
  | 'failed';

function problem(error: unknown): PlaylistProblem {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  const known: PlaylistProblem[] = [
    'forbidden',
    'changed_since',
    'unknown_playlist',
    'playlist_too_large',
    'invalid_file',
  ];
  return known.includes(detail as PlaylistProblem) ? (detail as PlaylistProblem) : 'failed';
}

const api = () => getServices().api;

export async function createPlaylist(
  name: string,
  visibility: Visibility = 'private',
): Promise<string | null> {
  const { data } = await api().POST('/api/v1/playlists', { body: { name, visibility } });
  return data?.id ?? null;
}

/** The owner's changes: name, sharing, folder (null: none). */
export async function updatePlaylist(
  playlistId: string,
  changes: { name?: string; visibility?: Visibility; folder_id?: string | null },
): Promise<PlaylistProblem | null> {
  const { error, response } = await api().PATCH('/api/v1/playlists/{playlist_id}', {
    params: { path: { playlist_id: playlistId } },
    body: changes,
  });
  return response.ok ? null : problem(error);
}

export async function deletePlaylist(playlistId: string): Promise<PlaylistProblem | null> {
  const { error, response } = await api().DELETE('/api/v1/playlists/{playlist_id}', {
    params: { path: { playlist_id: playlistId } },
  });
  return response.ok ? null : problem(error);
}

export interface EditResult {
  editId: string | null;
  problem: PlaylistProblem | null;
}

export async function addToPlaylist(
  playlistId: string,
  body: Schemas['EntriesIn'],
): Promise<EditResult> {
  const { data, error, response } = await api().POST('/api/v1/playlists/{playlist_id}/entries', {
    params: { path: { playlist_id: playlistId } },
    body,
  });
  return response.ok
    ? { editId: data?.edit_id ?? null, problem: null }
    : { editId: null, problem: problem(error) };
}

export async function removeEntries(playlistId: string, ids: string[]): Promise<EditResult> {
  const { data, error, response } = await api().POST(
    '/api/v1/playlists/{playlist_id}/entries/remove',
    { params: { path: { playlist_id: playlistId } }, body: { ids } },
  );
  return response.ok
    ? { editId: data?.edit_id ?? null, problem: null }
    : { editId: null, problem: problem(error) };
}

/** Move entries behind ``after`` (null: to the start). */
export async function moveEntries(
  playlistId: string,
  ids: string[],
  after: string | null,
): Promise<EditResult> {
  const { data, error, response } = await api().POST(
    '/api/v1/playlists/{playlist_id}/entries/move',
    { params: { path: { playlist_id: playlistId } }, body: { ids, after } },
  );
  return response.ok
    ? { editId: data?.edit_id ?? null, problem: null }
    : { editId: null, problem: problem(error) };
}

export async function undoEdit(editId: string): Promise<PlaylistProblem | null> {
  const { error, response } = await api().POST('/api/v1/playlists/edits/{edit_id}/undo', {
    params: { path: { edit_id: editId } },
  });
  return response.ok ? null : problem(error);
}

export async function createFolder(name: string): Promise<string | null> {
  const { data } = await api().POST('/api/v1/playlist-folders', { body: { name } });
  return data?.id ?? null;
}

export async function deleteFolder(folderId: string): Promise<boolean> {
  const { response } = await api().DELETE('/api/v1/playlist-folders/{folder_id}', {
    params: { path: { folder_id: folderId } },
  });
  return response.ok;
}

export interface Imported {
  id: string;
  entries: number;
  unmatched: string[];
}

/** A playlist file (M3U, M3U8, PLS, XSPF) as a new private playlist. */
export async function importPlaylist(
  name: string,
  file: File,
): Promise<Imported | PlaylistProblem> {
  const { data, error, response } = await api().POST('/api/v1/playlists/import', {
    params: { query: { name } },
    body: file as never,
    bodySerializer: (body: unknown) => body as BodyInit,
    headers: { 'Content-Type': 'application/octet-stream' },
  });
  return response.ok && data ? data : problem(error);
}

/** The export URL (fetched with the session; the file is offered for download). */
export async function exportPlaylist(playlistId: string): Promise<Blob | null> {
  const { data, response } = await api().GET('/api/v1/playlists/{playlist_id}/export.m3u8', {
    params: { path: { playlist_id: playlistId } },
    parseAs: 'blob',
  });
  return response.ok ? (data as unknown as Blob) : null;
}

export async function setFavorite(type: FavoriteTarget, id: string, on: boolean): Promise<boolean> {
  const params = { params: { path: { target_type: type, target_id: id } } };
  const { response } = on
    ? await api().PUT('/api/v1/favorites/{target_type}/{target_id}', params)
    : await api().DELETE('/api/v1/favorites/{target_type}/{target_id}', params);
  return response.ok;
}
