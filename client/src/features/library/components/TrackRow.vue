<template>
  <router-link
    v-if="context === 'library'"
    :to="{ name: 'library-release', params: { releaseId: track.release_id } }"
    class="library-row"
    :data-testid="`track-${track.id}`"
  >
    <span
      v-if="track.source_short || track.source"
      class="mono library-row__source"
      :title="sourceTitle"
      :aria-label="sourceTitle"
      data-testid="track-source"
      >{{ track.source_short ?? track.source }}</span
    >
    <span class="item-list__main">
      <span class="library-row__title">{{ track.title }}</span>
      <span class="text-muted item-list__sub library-row__title">
        {{ track.artist }} · {{ track.album }}
      </span>
    </span>
    <QualityBadge :effective="track.effective_quality" :status="track.quality_status" />
    <span class="mono text-muted library-row__format">{{ formatLabel(track) }}</span>
    <span class="mono text-muted library-row__duration">{{
      formatDuration(track.duration_ms)
    }}</span>
  </router-link>
  <div v-else class="library-row" :data-testid="`track-${track.id}`">
    <span
      v-if="track.source_short || track.source"
      class="mono library-row__source"
      :title="sourceTitle"
      :aria-label="sourceTitle"
      data-testid="track-source"
      >{{ track.source_short ?? track.source }}</span
    >
    <span class="mono text-muted library-row__number">
      {{ trackNumber(track.disc_number, track.track_number, discCount) }}
    </span>
    <span class="item-list__main">
      <span class="library-row__title">{{ track.title }}</span>
      <span
        v-if="track.artist !== track.album_artist"
        class="text-muted item-list__sub library-row__title"
        data-testid="track-artist"
      >
        {{ track.artist }}
      </span>
    </span>
    <QualityBadge :effective="track.effective_quality" :status="track.quality_status" />
    <span class="mono text-muted library-row__format">{{ formatLabel(track) }}</span>
    <span class="mono text-muted library-row__duration">{{
      formatDuration(track.duration_ms)
    }}</span>
  </div>
</template>

<script setup lang="ts">
import type { LibraryTrackRow } from '@anthology/api-types';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatDuration, formatLabel, trackNumber } from '../format';
import QualityBadge from './QualityBadge.vue';

/** `library`: a row of all tracks (links to its album); `release`: a row on the album page. */
const props = withDefaults(
  defineProps<{ track: LibraryTrackRow; context: 'library' | 'release'; discCount?: number }>(),
  { discCount: 1 },
);

const { t, d } = useI18n();
// Where the original was acquired (spec: sources, Downloads enter the library).
const sourceTitle = computed(() =>
  props.track.retrieved_at
    ? t('library.source', {
        source: props.track.source ?? '',
        date: d(new Date(props.track.retrieved_at)),
      })
    : (props.track.source ?? ''),
);
</script>

<style scoped>
.library-row__source {
  padding: 1px var(--space-1);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}
</style>
