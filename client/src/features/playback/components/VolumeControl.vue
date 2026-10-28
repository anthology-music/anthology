<template>
  <span class="volume-control">
    <q-btn
      flat
      round
      size="sm"
      :icon="muted ? 'volume_off' : 'volume_up'"
      :aria-label="
        muted
          ? t('playback.outputs.unmute', { name: label })
          : t('playback.outputs.mute', { name: label })
      "
      :aria-pressed="muted"
      :disable="disabled"
      :data-testid="`${testid}-mute`"
      @click="emit('change', { muted: !muted })"
    />
    <q-slider
      :model-value="volume ?? 0"
      :min="0"
      :max="100"
      :step="1"
      :disable="disabled || volume === null"
      :aria-label="label"
      class="volume-control__slider"
      :data-testid="testid"
      @change="(value: number | null) => emit('change', { volume: value ?? 0 })"
    />
  </span>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

/** Volume (0–100) and mute of a zone or a room. */
defineProps<{
  label: string;
  volume: number | null;
  muted: boolean;
  disabled?: boolean;
  testid: string;
}>();
const emit = defineEmits<{ change: [change: { volume?: number; muted?: boolean }] }>();
const { t } = useI18n();
</script>

<style scoped>
.volume-control {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.volume-control__slider {
  width: 120px;
}
</style>
