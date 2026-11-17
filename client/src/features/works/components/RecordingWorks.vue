<template>
  <template v-if="rows.length">
    <q-item-label header>{{ t('works.ofRecording') }}</q-item-label>
    <q-item
      v-for="row in rows"
      :key="row.id"
      v-close-popup
      clickable
      :to="{ name: 'work', params: { workId: row.work.id } }"
      :data-testid="`track-work-${row.work.title}`"
    >
      <q-item-section avatar><q-icon :name="WORK_ICONS[row.work.type]" /></q-item-section>
      <q-item-section>{{ row.work.title }}</q-item-section>
    </q-item>
  </template>
</template>

<script setup lang="ts">
import type { RecordingWorkRow } from '@anthology/api-types';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { useSubscription } from '@/sync/useSubscription';

import { WORK_ICONS } from '../icons';

/** The works of a recording as menu entries (track menus); subscribed while the menu is
 * open (spec: works, Navigation between works and recordings). */
const props = defineProps<{ recordingId: string }>();
const LIMIT = 20;
const { t } = useI18n();
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
