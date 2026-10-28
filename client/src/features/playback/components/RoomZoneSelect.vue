<template>
  <select
    class="room-zone__select"
    :aria-label="t('playback.outputs.roomZone', { name: room.name })"
    :value="room.zone_id ?? NONE"
    :disabled="disabled"
    :data-testid="`room-zone-${room.name}`"
    @change="change(($event.target as HTMLSelectElement).value)"
  >
    <option v-for="zone in zones" :key="zone.id" :value="zone.id">{{ zone.name }}</option>
    <option :value="ALONE">{{ t('playback.outputs.ownZone') }}</option>
    <option :value="NONE">{{ t('playback.outputs.noZone') }}</option>
  </select>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import type { OutputRow } from '../outputs';

/** Which zone a room plays in: one of its system's zones, a zone of its own, or none. */
const props = defineProps<{ room: OutputRow; zones: OutputRow[]; disabled?: boolean }>();
const emit = defineEmits<{ join: [zoneId: string | null]; leave: [] }>();
const { t } = useI18n();

const NONE = '';
const ALONE = 'alone';

function change(value: string): void {
  if (value === NONE) {
    if (props.room.zone_id !== null) emit('leave');
  } else if (value === ALONE) {
    emit('join', null);
  } else if (value !== props.room.zone_id) {
    emit('join', value);
  }
}
</script>

<style scoped>
.room-zone__select {
  min-height: 44px;
  padding: 0 var(--space-2);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
</style>
