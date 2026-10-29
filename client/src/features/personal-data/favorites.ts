import type { FavoriteRow } from '@anthology/api-types';
import { defineStore } from 'pinia';
import { reactive, ref } from 'vue';

import { getServices } from '@/services';
import type { Subscription } from '@/sync/subscription';

import { type FavoriteTarget, setFavorite } from './api';

/** Favorites are few next to the library: the store holds them all as one window. */
export const WINDOW = 10_000;

const key = (type: FavoriteTarget, id: string) => `${type}:${id}`;

/**
 * The user's favorites (spec: personal-data, Favorites; private), live from
 * `personal.favorites`; marks are toggled optimistically and roll back on error.
 */
export const useFavoritesStore = defineStore('favorites', () => {
  const marked = reactive(new Set<string>());
  // Toggles not confirmed by the stream yet.
  const pending = reactive(new Map<string, boolean>());
  const failed = ref(false);
  let subscription: Subscription | null = null;

  function start(): void {
    if (subscription) return;
    subscription = getServices().sync.subscribe('personal.favorites', {}, [0, WINDOW], {
      cache: false,
    });
    subscription.onChange(() => {
      marked.clear();
      for (const row of subscription!.rows.values()) {
        const favorite = row as unknown as FavoriteRow;
        marked.add(key(favorite.target_type, favorite.target_id));
      }
    });
  }

  function has(type: FavoriteTarget, id: string): boolean {
    const name = key(type, id);
    return pending.has(name) ? pending.get(name)! : marked.has(name);
  }

  async function toggle(type: FavoriteTarget, id: string): Promise<void> {
    start();
    const name = key(type, id);
    const on = !has(type, id);
    pending.set(name, on);
    failed.value = !(await setFavorite(type, id, on));
    pending.delete(name);
    if (!failed.value) {
      if (on) marked.add(name);
      else marked.delete(name);
    }
  }

  return { has, toggle, start, failed };
});
