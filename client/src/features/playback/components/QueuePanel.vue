<template>
  <section class="queue-panel" :aria-label="t('playback.queue')" data-testid="queue-panel">
    <p v-if="subscription.total === 0" class="text-muted">{{ t('playback.emptyQueue') }}</p>
    <div v-else class="queue-panel__list">
      <VirtualList :subscription="subscription" :label="t('playback.queue')">
        <template #default="{ row }">
          <div
            class="queue-panel__row"
            :class="{ 'queue-panel__row--current': row.id === player.loaded }"
            :data-testid="`queue-entry-${row.id}`"
          >
            <button
              type="button"
              class="queue-panel__play"
              :aria-label="t('playback.playFromHere', { title: entry(row).track.title })"
              @click="player.playEntry(String(row.id))"
            >
              <span class="queue-panel__title">{{ entry(row).track.title }}</span>
              <span class="text-muted queue-panel__sub">
                {{ entry(row).track.artist }} · {{ entry(row).track.album }}
              </span>
            </button>
            <span
              v-if="player.problems.get(String(row.id))"
              class="text-muted queue-panel__problem"
            >
              {{ t(`playback.problem.${player.problems.get(String(row.id))}`) }}
            </span>
            <q-btn
              flat
              round
              size="sm"
              icon="close"
              :aria-label="t('playback.remove', { title: entry(row).track.title })"
              :data-testid="`queue-remove-${row.id}`"
              @click="player.removeEntry(String(row.id))"
            />
          </div>
        </template>
      </VirtualList>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { PlayQueueEntryRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { useSubscription } from '@/sync/useSubscription';

import { usePlayerStore } from '../store';

/** The entries of this device's queue (one generation; a rewritten queue mounts anew). */
const props = defineProps<{ generation: string }>();

const { t } = useI18n();
const player = usePlayerStore();
const subscription = useSubscription('playback.queue', { generation: props.generation }, [0, 100], {
  cache: false,
});
const entry = (row: Record<string, unknown>) => row as unknown as PlayQueueEntryRow;
</script>

<style scoped>
.queue-panel__list {
  height: 40vh;
  min-height: 200px;
}

.queue-panel__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target);
  border-radius: var(--radius-sm);
}

.queue-panel__row--current {
  background: var(--color-hover);
}

.queue-panel__play {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.queue-panel__title,
.queue-panel__sub {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.queue-panel__problem {
  font-size: var(--text-xs);
}
</style>
