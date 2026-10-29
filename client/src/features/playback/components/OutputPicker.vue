<template>
  <q-btn
    flat
    round
    :icon="player.outputZone ? 'speaker_group' : 'devices'"
    :color="player.outputZone ? 'primary' : undefined"
    :aria-label="t('playback.outputs.choose')"
    data-testid="output-picker"
  >
    <q-menu anchor="top right" self="bottom right">
      <q-list class="output-picker" role="listbox" :aria-label="t('playback.outputs.choose')">
        <q-item
          v-close-popup
          clickable
          role="option"
          :aria-selected="player.outputZone === null"
          :active="player.outputZone === null"
          data-testid="output-device"
          @click="choose(null)"
        >
          <q-item-section avatar><q-icon name="devices" aria-hidden="true" /></q-item-section>
          <q-item-section>{{ t('playback.outputs.thisDevice') }}</q-item-section>
        </q-item>
        <q-item
          v-for="zone in outputs.zones"
          :key="zone.id"
          v-close-popup
          clickable
          role="option"
          :disable="!zone.online"
          :aria-selected="player.outputZone === zone.id"
          :active="player.outputZone === zone.id"
          :data-testid="`output-zone-${zone.name}`"
          @click="choose(zone.id)"
        >
          <q-item-section avatar>
            <q-icon :name="zone.online ? 'speaker_group' : 'cloud_off'" aria-hidden="true" />
          </q-item-section>
          <q-item-section>
            <q-item-label>{{ zone.name }}</q-item-label>
            <q-item-label caption>
              <template v-if="zone.online">{{ zone.system?.name }}</template>
              <template v-else>
                {{ t('playback.outputs.offline') }}
                <template v-if="zone.system?.reason">({{ zone.system.reason }})</template>
              </template>
            </q-item-label>
          </q-item-section>
        </q-item>
        <q-item v-if="outputs.zones.length === 0" class="text-muted">
          <q-item-section>{{ t('playback.outputs.none') }}</q-item-section>
        </q-item>
        <q-separator v-if="outputs.zones.length || outputs.freeRooms.length" />
        <q-item
          v-if="outputs.zones.length || outputs.freeRooms.length"
          v-close-popup
          clickable
          data-testid="output-manage"
          @click="managing = true"
        >
          <q-item-section avatar><q-icon name="tune" aria-hidden="true" /></q-item-section>
          <q-item-section>{{ t('playback.outputs.manage') }}</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
  <q-dialog v-model="managing">
    <ZoneManager :outputs="outputs" />
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import type { Outputs } from '../outputs';
import { usePlayerStore } from '../store';
import ZoneManager from './ZoneManager.vue';

/** "This device" and every zone of every output system (spec: playback, Output picker). */
defineProps<{ outputs: Outputs }>();

const { t } = useI18n();
const player = usePlayerStore();
const managing = ref(false);

async function choose(zoneId: string | null): Promise<void> {
  if (zoneId === player.outputZone) return;
  await player.selectOutput(zoneId);
}
</script>

<style scoped>
.output-picker {
  min-width: 260px;
}
</style>
