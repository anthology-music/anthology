import { computed, type ComputedRef } from 'vue';

import { useSubscription } from './useSubscription';

export type ServiceState = 'available' | 'unavailable' | 'incompatible';

export interface ServiceRow {
  id: string;
  name: string;
  status: ServiceState;
  version: string | null;
  interface: string | null;
  message: string | null;
  changed_at: string;
}

/** Live status of the services the installation uses (stream `services`, spec: sync-protocol). */
export function useServices(): ComputedRef<ServiceRow[]> {
  const subscription = useSubscription('services', {}, [0, 100]);
  return computed(() =>
    [...subscription.value.rows.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, row]) => row as unknown as ServiceRow),
  );
}

/** True while the named service is available; features use it to hide their actions. */
export function useServiceAvailable(name: string): ComputedRef<boolean> {
  const services = useServices();
  return computed(() => services.value.some((s) => s.name === name && s.status === 'available'));
}
