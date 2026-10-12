import { onBeforeUnmount, shallowRef, triggerRef, type ShallowRef } from 'vue';

import { getServices } from '@/services';

import type { Subscription } from './subscription';

/**
 * Subscribe to a stream for the lifetime of the calling component. The returned ref is
 * triggered on every change (counts, rows, deltas); read `total`, `rows`, `source`.
 */
export function useSubscription(
  stream: string,
  params: Record<string, unknown> = {},
  window: [number, number] = [0, 100],
): ShallowRef<Subscription> {
  const { sync } = getServices();
  const subscription = shallowRef(sync.subscribe(stream, params, window));
  const stop = subscription.value.onChange(() => triggerRef(subscription));
  onBeforeUnmount(() => {
    stop();
    sync.unsubscribe(subscription.value);
  });
  return subscription;
}
