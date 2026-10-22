<template>
  <span
    v-if="status === 'suspicious'"
    class="quality-badge quality-badge--check"
    :title="t('library.quality.checkHint')"
    data-testid="quality-check"
  >
    <q-icon name="help_outline" size="14px" aria-hidden="true" />{{ t('library.quality.check') }}
  </span>
  <span
    v-else-if="effective"
    class="quality-badge"
    :class="{ 'quality-badge--upscaled': status === 'upscaled' }"
    :title="status === 'upscaled' ? t('library.quality.upscaledHint') : undefined"
    data-testid="quality-badge"
  >
    <q-icon v-if="status === 'upscaled'" name="warning_amber" size="14px" aria-hidden="true" />{{
      t(`library.quality.tiers.${effective}`)
    }}
  </span>
</template>

<script setup lang="ts">
import type { LibraryTrackRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

/** The effective quality (spec: library, Quality badge); nothing before a conclusive analysis. */
defineProps<{
  effective: LibraryTrackRow['effective_quality'];
  status: LibraryTrackRow['quality_status'];
}>();
const { t } = useI18n();
</script>

<style scoped>
.quality-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--color-active-bg);
  color: var(--color-accent-strong);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.quality-badge--upscaled,
.quality-badge--check {
  background: none;
  border: 1px solid currentColor;
  color: var(--color-status-warning);
}
</style>
