<template>
  <div class="playable-row">
    <q-btn
      flat
      round
      size="sm"
      icon="play_arrow"
      :aria-label="t('playback.playTrack', { title: track.title })"
      :data-testid="`play-${track.id}`"
      @click="play"
    />
    <TrackRow
      class="playable-row__track"
      :track="track"
      :context="context"
      :disc-count="discCount"
    />
    <q-btn
      flat
      round
      size="sm"
      icon="more_vert"
      :aria-label="t('playback.more', { title: track.title })"
      :data-testid="`more-${track.id}`"
    >
      <q-menu>
        <q-list>
          <q-item
            v-close-popup
            clickable
            :data-testid="`play-next-${track.id}`"
            @click="player.enqueue('next', [track.id])"
          >
            <q-item-section>{{ t('playback.playNext') }}</q-item-section>
          </q-item>
          <q-item
            v-close-popup
            clickable
            :data-testid="`play-append-${track.id}`"
            @click="player.enqueue('append', [track.id])"
          >
            <q-item-section>{{ t('playback.addToQueue') }}</q-item-section>
          </q-item>
          <q-item
            v-close-popup
            clickable
            :disable="downloads.busy"
            :data-testid="`download-${track.id}`"
            @click="downloads.downloadTrack(track.id)"
          >
            <q-item-section>{{ t('library.download.track') }}</q-item-section>
          </q-item>
        </q-list>
      </q-menu>
    </q-btn>
  </div>
</template>

<script setup lang="ts">
import type { LibraryTrackRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import TrackRow from '@/features/library/components/TrackRow.vue';
import { useDownloadStore } from '@/features/library/downloads';

import { type PlayRule, usePlayerStore } from '../store';

/** A track row with play actions: plays the list it is in (``rule``) from this track. */
const props = withDefaults(
  defineProps<{
    track: LibraryTrackRow;
    context: 'library' | 'release';
    rule?: PlayRule | null;
    discCount?: number;
  }>(),
  { rule: null, discCount: 1 },
);

const { t } = useI18n();
const player = usePlayerStore();
const downloads = useDownloadStore();

function play(): void {
  if (props.rule) void player.playList(props.rule, props.track.id);
  else void player.playTracks([props.track.id]);
}
</script>

<style scoped>
.playable-row {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.playable-row__track {
  flex: 1;
  min-width: 0;
}
</style>
