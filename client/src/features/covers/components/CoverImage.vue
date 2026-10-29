<template>
  <span
    class="cover"
    :class="{ 'cover--round': round }"
    :style="{ width: `${px}px`, height: `${px}px` }"
    :data-testid="testid"
  >
    <img
      v-if="src && !failed"
      :src="src"
      :alt="alt"
      loading="lazy"
      decoding="async"
      class="cover__image"
      :width="px"
      :height="px"
      @error="failed = true"
    />
    <span v-else class="cover__placeholder" role="img" :aria-label="alt" data-cover="placeholder">
      <span v-if="px >= 96" class="cover__title">{{ title }}</span>
      <span v-if="px >= 96 && artist" class="cover__artist">{{ artist }}</span>
      <span v-if="px < 96" class="cover__initial" aria-hidden="true">{{ initial }}</span>
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { type ImageSize, useImageGrant } from '../grant';

/**
 * A cover at ``px`` pixels: the thumbnail of the next size up, loaded lazily, or a placeholder
 * with album title and artist (spec: covers, Placeholder).
 */
const props = withDefaults(
  defineProps<{
    imageId: string | null | undefined;
    title: string;
    artist?: string;
    px?: number;
    round?: boolean;
    testid?: string;
  }>(),
  { artist: '', px: 40, round: false, testid: 'cover' },
);

const { t } = useI18n();
const grant = useImageGrant();
const failed = ref(false);

const size = computed<ImageSize>(() => {
  const needed = props.px * (globalThis.devicePixelRatio || 1);
  return needed <= 64 ? 64 : needed <= 256 ? 256 : 600;
});
const src = computed(() => (props.imageId ? grant.url(props.imageId, size.value) : null));
const alt = computed(() => t('covers.alt', { title: props.title, artist: props.artist || '–' }));
const initial = computed(() => props.title.trim().charAt(0).toUpperCase() || '♪');

watch(
  () => props.imageId,
  () => {
    failed.value = false;
  },
);
</script>

<style scoped>
.cover {
  display: inline-flex;
  flex: none;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-hover);
}

.cover--round {
  border-radius: 50%;
}

.cover__image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: var(--space-2);
  text-align: center;
  color: var(--color-text-secondary);
  background: var(--color-active-bg);
}

.cover__title {
  overflow: hidden;
  font-weight: var(--weight-medium);
  color: var(--color-text);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.cover__artist {
  overflow: hidden;
  font-size: var(--text-sm);
  white-space: nowrap;
  text-overflow: ellipsis;
  max-width: 100%;
}

.cover__initial {
  font-weight: var(--weight-medium);
}
</style>
