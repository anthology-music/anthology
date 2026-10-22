<template>
  <router-link
    v-if="context === 'library'"
    :to="{ name: 'library-release', params: { releaseId: track.release_id } }"
    class="library-row"
    :data-testid="`track-${track.id}`"
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

import { formatDuration, formatLabel, trackNumber } from '../format';
import QualityBadge from './QualityBadge.vue';

/** `library`: a row of all tracks (links to its album); `release`: a row on the album page. */
withDefaults(
  defineProps<{ track: LibraryTrackRow; context: 'library' | 'release'; discCount?: number }>(),
  { discCount: 1 },
);
</script>
