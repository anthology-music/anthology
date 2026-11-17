<template>
  <span v-if="rows.length" class="player-works" data-testid="player-works">
    <q-icon name="library_music" aria-hidden="true" />
    <router-link
      v-for="row in rows"
      :key="row.id"
      :to="{ name: 'work', params: { workId: row.work.id } }"
      class="player-works__link"
    >
      {{ row.work.title }}
    </router-link>
  </span>
</template>

<script setup lang="ts">
import type { RecordingWorkRow } from '@anthology/api-types';
import { computed } from 'vue';

import { useSubscription } from '@/sync/useSubscription';

/** The works of the playing recording, as links in the player bar. */
const props = defineProps<{ recordingId: string }>();
const LIMIT = 3;
const subscription = useSubscription('works.recording', { recording_id: props.recordingId }, [
  0,
  LIMIT,
]);
const rows = computed(
  () =>
    [...Array(Math.min(LIMIT, subscription.value.total ?? 0)).keys()]
      .map((position) => subscription.value.rows.get(position))
      .filter((row) => row !== undefined) as unknown as RecordingWorkRow[],
);
</script>

<style scoped>
.player-works {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  font-size: var(--text-sm);
}

.player-works__link + .player-works__link::before {
  content: '· ';
}
</style>
