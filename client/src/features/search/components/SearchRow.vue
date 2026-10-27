<template>
  <ArtistRow v-if="type === 'artist'" :artist="row as unknown as LibraryArtistRow" />
  <ReleaseRow
    v-else-if="type === 'release'"
    :release="row as unknown as LibraryReleaseRow"
    show-artist
  />
  <PlayableTrackRow
    v-else
    :track="row as unknown as LibraryTrackRow"
    context="library"
    :rule="rule ?? null"
  />
</template>

<script setup lang="ts">
import type { LibraryArtistRow, LibraryReleaseRow, LibraryTrackRow } from '@anthology/api-types';

import ArtistRow from '@/features/library/components/ArtistRow.vue';
import ReleaseRow from '@/features/library/components/ReleaseRow.vue';
import PlayableTrackRow from '@/features/playback/components/PlayableTrackRow.vue';
import type { PlayRule } from '@/features/playback/store';

import type { ItemType } from '../query';

/** A search result shown with the library's row of its type; tracks play the results
 * (``rule``) from this track. */
defineProps<{ type: ItemType; row: Record<string, unknown>; rule?: PlayRule | null }>();
</script>
