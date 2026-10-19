import { computed, ref, watch } from 'vue';

import { useSubscription } from '@/sync/useSubscription';

export type EntryState = 'loading' | 'ready' | 'missing' | 'removed';

/**
 * One artist or release from an entry stream (`library.artist`, `library.release`):
 * the row, and whether it does not exist or was removed while open.
 */
export function useEntry<T>(stream: string, params: Record<string, unknown>) {
  const subscription = useSubscription(stream, params, [0, 1]);
  const seen = ref(false);
  const entry = computed(() =>
    subscription.value.total ? (subscription.value.rows.get(0) as T | undefined) : undefined,
  );
  watch(entry, (row) => {
    if (row) seen.value = true;
  });
  const state = computed<EntryState>(() => {
    if (subscription.value.total === null) return 'loading';
    if (subscription.value.total === 0) return seen.value ? 'removed' : 'missing';
    return 'ready';
  });
  return { entry, state };
}
