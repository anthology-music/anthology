<template>
  <q-card class="zone-manager" data-testid="zone-manager">
    <q-card-section>
      <h2 class="zone-manager__title">{{ t('playback.outputs.manage') }}</h2>
      <p v-if="problem" class="zone-manager__problem" role="alert" data-testid="zone-problem">
        <q-icon name="error" aria-hidden="true" /> {{ t(`playback.outputs.problem.${problem}`) }}
      </p>
    </q-card-section>
    <q-card-section v-for="zone in outputs.zones" :key="zone.id" class="zone-manager__zone">
      <div class="zone-manager__row" :data-testid="`zone-${zone.name}`">
        <span class="zone-manager__name">
          <q-icon :name="zone.online ? 'speaker_group' : 'cloud_off'" aria-hidden="true" />
          {{ zone.name }}
          <span v-if="!zone.online" class="text-muted">· {{ t('playback.outputs.offline') }}</span>
        </span>
        <VolumeControl
          :label="t('playback.outputs.zoneVolume', { name: zone.name })"
          :volume="zone.volume ?? null"
          :muted="zone.muted ?? false"
          :disabled="!zone.online"
          :testid="`zone-volume-${zone.name}`"
          @change="(change) => run(setZoneVolume(zone.id, change))"
        />
      </div>
      <ul class="zone-manager__rooms">
        <li v-for="room in zone.rooms" :key="room.id" class="zone-manager__row">
          <span class="zone-manager__name">{{ room.name }}</span>
          <VolumeControl
            :label="t('playback.outputs.roomVolume', { name: room.name })"
            :volume="room.volume ?? null"
            :muted="room.muted ?? false"
            :disabled="!zone.online"
            :testid="`room-volume-${room.name}`"
            @change="(change) => run(setRoomVolume(room.id, change))"
          />
          <RoomZoneSelect
            :room="room"
            :zones="zonesOf(room)"
            :disabled="!zone.online"
            @join="(zoneId) => run(joinZone(room.id, zoneId))"
            @leave="run(leaveZone(room.id))"
          />
        </li>
      </ul>
    </q-card-section>
    <q-card-section v-if="outputs.freeRooms.length">
      <h3 class="zone-manager__subtitle">{{ t('playback.outputs.freeRooms') }}</h3>
      <ul class="zone-manager__rooms">
        <li v-for="room in outputs.freeRooms" :key="room.id" class="zone-manager__row">
          <span class="zone-manager__name">{{ room.name }}</span>
          <RoomZoneSelect
            :room="room"
            :zones="zonesOf(room)"
            :disabled="!room.online"
            @join="(zoneId) => run(joinZone(room.id, zoneId))"
            @leave="run(leaveZone(room.id))"
          />
        </li>
      </ul>
    </q-card-section>
    <q-card-actions align="right">
      <q-btn v-close-popup flat :label="t('playback.outputs.close')" />
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import {
  joinZone,
  leaveZone,
  type OutputProblem,
  type OutputRow,
  type Outputs,
  setRoomVolume,
  setZoneVolume,
} from '../outputs';
import RoomZoneSelect from './RoomZoneSelect.vue';
import VolumeControl from './VolumeControl.vue';

/** Zones, rooms and their volumes; every signed-in user may change them (spec: Zone
 * management). The result arrives through the outputs stream. */
const props = defineProps<{ outputs: Outputs }>();

const { t } = useI18n();
const problem = ref<OutputProblem | null>(null);

function zonesOf(room: OutputRow) {
  return props.outputs.zones.filter((zone) => zone.system_id === room.system_id);
}

async function run(action: Promise<OutputProblem | null>): Promise<void> {
  problem.value = await action;
}
</script>

<style scoped>
.zone-manager {
  width: min(560px, 100vw);
}

.zone-manager__title {
  margin: 0;
  font-size: var(--text-lg);
}

.zone-manager__subtitle {
  margin: 0 0 var(--space-2);
  font-size: var(--text-md);
}

.zone-manager__problem {
  margin: var(--space-2) 0 0;
  color: var(--color-status-error);
}

.zone-manager__zone {
  border-top: 1px solid var(--color-border);
}

.zone-manager__rooms {
  margin: 0;
  padding: 0 0 0 var(--space-4);
  list-style: none;
}

.zone-manager__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  min-height: 44px;
}

.zone-manager__name {
  display: inline-flex;
  flex: 1;
  align-items: center;
  gap: var(--space-2);
  min-width: 140px;
}
</style>
