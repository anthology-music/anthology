import type { PlaylistFolderRow, PlaylistRow } from '@anthology/api-types';
import { computed, type ComputedRef } from 'vue';

import { useSubscription } from '@/sync/useSubscription';

/** Own and shared playlists, and own folders, live (playlists are few: one window each). */
export function usePlaylists(): {
  playlists: ComputedRef<PlaylistRow[]>;
  folders: ComputedRef<PlaylistFolderRow[]>;
} {
  const lists = useSubscription('personal.playlists', {}, [0, 2_000], { cache: false });
  const folders = useSubscription('personal.playlist_folders', {}, [0, 500], { cache: false });
  const sorted = <T>(subscription: typeof lists) =>
    [...subscription.value.rows.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, row]) => row as unknown as T);
  return {
    playlists: computed(() => sorted<PlaylistRow>(lists)),
    folders: computed(() => sorted<PlaylistFolderRow>(folders)),
  };
}
