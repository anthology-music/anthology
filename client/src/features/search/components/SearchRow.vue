<template>
  <ArtistRow v-if="type === 'artist'" :artist="row as unknown as LibraryArtistRow" />
  <ReleaseRow
    v-else-if="type === 'release'"
    :release="row as unknown as LibraryReleaseRow"
    show-artist
  />
  <TrackRow v-else :track="row as unknown as LibraryTrackRow" context="library" />
</template>

<script setup lang="ts">
import type { LibraryArtistRow, LibraryReleaseRow, LibraryTrackRow } from '@anthology/api-types';

import ArtistRow from '@/features/library/components/ArtistRow.vue';
import ReleaseRow from '@/features/library/components/ReleaseRow.vue';
import TrackRow from '@/features/library/components/TrackRow.vue';

import type { ItemType } from '../query';

/** A search result shown with the library's row of its type. */
defineProps<{ type: ItemType; row: Record<string, unknown> }>();
</script>
