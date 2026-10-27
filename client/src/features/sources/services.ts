import type { Schemas, SourceServiceRow } from '@anthology/api-types';
import { computed } from 'vue';

import { useSubscription } from '@/sync/useSubscription';

export type Offered = Schemas['Offered'];

/** The configured source services (spec: sources, Source status). */
export function useSourceServices() {
  const subscription = useSubscription('sources.services', {}, [0, 50]);
  const all = computed(() =>
    [...subscription.value.rows.values()].map((row) => row as unknown as SourceServiceRow),
  );
  const available = computed(() => all.value.filter((service) => service.available));
  return { subscription, all, available };
}

/** "FLAC 24/96", "AAC 256" (an offered quality of interface v1). */
export function qualityLabel(offered: Offered | null | undefined): string {
  if (!offered?.format) return '';
  const format = offered.format.toUpperCase();
  if (offered.lossless) {
    const depth = offered.bit_depth ?? 16;
    const rate = (offered.sample_rate_hz ?? 44_100) / 1000;
    return `${format} ${depth}/${Number.isInteger(rate) ? rate : rate.toFixed(1)}`;
  }
  return offered.bitrate_kbps ? `${format} ${offered.bitrate_kbps}` : format;
}

export const isLink = (text: string) => /^https?:\/\//i.test(text.trim());
