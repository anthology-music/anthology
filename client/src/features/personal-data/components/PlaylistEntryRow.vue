<template>
  <div
    class="library-row playlist-entry"
    :class="{ 'playlist-entry--target': target }"
    draggable="true"
    :data-testid="`entry-${entry.id}`"
    @dragstart="start"
    @dragover.prevent="target = true"
    @dragleave="target = false"
    @drop.prevent="drop"
  >
    <q-icon name="drag_indicator" class="playlist-entry__handle" aria-hidden="true" />
    <q-btn
      flat
      round
      size="sm"
      icon="play_arrow"
      :aria-label="t('playback.playTrack', { title: entry.track.title })"
      :data-testid="`entry-play-${entry.id}`"
      @click="emit('play')"
    />
    <CoverImage
      :image-id="entry.track.cover"
      :title="entry.track.album"
      :artist="entry.track.album_artist"
      :px="40"
    />
    <span class="item-list__main">
      <span class="library-row__title">{{ entry.track.title }}</span>
      <span class="text-muted item-list__sub library-row__title">
        {{ entry.track.artist }} · {{ entry.track.album }}
        <template v-if="entry.added_by_name">
          ·
          <span data-testid="entry-added-by">{{
            t('personal.playlists.addedBy', { name: entry.added_by_name })
          }}</span>
        </template>
      </span>
    </span>
    <span class="mono text-muted library-row__duration">
      {{ formatDuration(entry.track.duration_ms) }}
    </span>
    <q-btn
      flat
      round
      size="sm"
      icon="arrow_upward"
      :disable="first"
      :aria-label="t('personal.playlists.up', { title: entry.track.title })"
      :data-testid="`entry-up-${entry.id}`"
      @click="emit('up')"
    />
    <q-btn
      flat
      round
      size="sm"
      icon="arrow_downward"
      :disable="last"
      :aria-label="t('personal.playlists.down', { title: entry.track.title })"
      :data-testid="`entry-down-${entry.id}`"
      @click="emit('down')"
    />
    <q-btn
      flat
      round
      size="sm"
      icon="remove_circle_outline"
      :aria-label="t('personal.playlists.remove', { title: entry.track.title })"
      :data-testid="`entry-remove-${entry.id}`"
      @click="emit('remove')"
    />
  </div>
</template>

<script setup lang="ts">
import type { PlaylistEntryRow } from '@anthology/api-types';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import CoverImage from '@/features/covers/components/CoverImage.vue';
import { formatDuration } from '@/features/library/format';

/** One playlist entry: drag it onto another to place it behind that one, or move it with the
 * buttons (keyboard and touch). */
const props = defineProps<{ entry: PlaylistEntryRow; first: boolean; last: boolean }>();
const emit = defineEmits<{ play: []; remove: []; up: []; down: []; drop: [dragged: string] }>();

const { t } = useI18n();
const target = ref(false);
const TYPE = 'application/x-anthology-entry';

function start(event: DragEvent): void {
  event.dataTransfer?.setData(TYPE, props.entry.id);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
}

function drop(event: DragEvent): void {
  target.value = false;
  const dragged = event.dataTransfer?.getData(TYPE);
  if (dragged) emit('drop', dragged);
}
</script>

<style scoped>
.playlist-entry__handle {
  cursor: grab;
  color: var(--color-text-muted);
}

.playlist-entry--target {
  box-shadow: inset 0 -2px 0 var(--color-selection-ring);
}
</style>
