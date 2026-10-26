import { computed, type ShallowRef } from 'vue';

import { useCounts } from '@/features/library/numbers';
import type { Subscription } from '@/sync/subscription';

/** The count of a result list: "10.000+" when the server capped it. */
export function useResultCount(subscription: ShallowRef<Subscription>) {
  const { number } = useCounts();
  return computed(() => {
    const { total, counters } = subscription.value;
    return counters.capped ? `${number(total)}+` : number(total);
  });
}
