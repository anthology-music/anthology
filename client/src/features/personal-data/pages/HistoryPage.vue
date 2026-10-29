<template>
  <section class="library-section">
    <h1 class="library-section__title">{{ t('personal.history.title') }}</h1>
    <p class="text-muted">{{ t('personal.history.hint') }}</p>
    <LibraryList
      stream="personal.history"
      position-key="history"
      :label="t('personal.history.title')"
      :empty="t('personal.history.empty')"
      uncached
    >
      <template #default="{ row }">
        <div class="library-row" :data-testid="`play-${row.id}`">
          <span class="mono text-muted history__when">
            {{ when(String(row.played_at)) }}
          </span>
          <TrackRow
            class="history__track"
            :track="(row as unknown as PlayRow).track"
            context="library"
          />
          <span v-if="row.zone" class="text-muted history__zone">
            <q-icon name="speaker_group" aria-hidden="true" /> {{ row.zone }}
          </span>
        </div>
      </template>
    </LibraryList>
  </section>
</template>

<script setup lang="ts">
import type { PlayRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import LibraryList from '@/features/library/components/LibraryList.vue';
import TrackRow from '@/features/library/components/TrackRow.vue';

/** What the user played, newest first (spec: personal-data, Play history). */
const { t, locale } = useI18n();

function when(value: string): string {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value),
  );
}
</script>

<style scoped>
.history__when {
  flex: none;
  width: 9em;
}

.history__track {
  flex: 1;
  min-width: 0;
}

.history__zone {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  white-space: nowrap;
}
</style>
