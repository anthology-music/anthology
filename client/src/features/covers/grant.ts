import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getServices } from '@/services';

/** The grant is renewed when it expires within this time. */
export const RENEW_MS = 5 * 60_000;

export type ImageSize = 64 | 256 | 600 | 'full';

interface Grant {
  prefix: string;
  query: string;
  expires: number;
}

/**
 * One signed grant for every image URL of this device (spec: covers, Sizes and delivery):
 * the client builds `{prefix}/{image}/{size}?{params}` itself, so lists need no request per
 * image. Renewed before it expires.
 */
export const useImageGrant = defineStore('imageGrant', () => {
  const grant = ref<Grant | null>(null);
  let pending: Promise<void> | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function load(): Promise<void> {
    const { data } = await getServices().api.POST('/api/v1/covers/grant');
    if (!data) return;
    const expires = Date.parse(data.expires_at);
    grant.value = {
      prefix: data.prefix,
      query: new URLSearchParams(data.params).toString(),
      expires,
    };
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void refresh(), Math.max(expires - Date.now() - RENEW_MS, 1_000));
  }

  function refresh(): Promise<void> {
    pending ??= load().finally(() => {
      pending = null;
    });
    return pending;
  }

  /** The URL of an image, or null until the grant arrived (it is requested then). */
  function url(imageId: string, size: ImageSize, format: 'webp' | 'jpeg' = 'webp'): string | null {
    const current = grant.value;
    if (!current || current.expires - Date.now() < RENEW_MS) {
      void refresh();
      if (!current) return null;
    }
    const kind = format === 'jpeg' ? 'format=jpeg&' : '';
    return `${current.prefix}/${imageId}/${size}?${kind}${current.query}`;
  }

  return { grant, url, refresh };
});
