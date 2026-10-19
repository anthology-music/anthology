<template>
  <router-link
    :to="{ name: 'library-artist', params: { artistId: artist.id } }"
    class="library-row"
    :data-testid="`artist-${artist.id}`"
  >
    <q-icon name="person" size="20px" class="library-row__icon" aria-hidden="true" />
    <span class="item-list__main">
      <span class="library-row__title">{{ artist.name }}</span>
      <span class="text-muted item-list__sub">
        {{ count('releases', artist.release_count) }} · {{ count('tracks', artist.track_count) }}
      </span>
    </span>
  </router-link>
</template>

<script setup lang="ts">
import type { LibraryArtistRow } from '@anthology/api-types';

import { useCounts } from '../numbers';

defineProps<{ artist: LibraryArtistRow }>();

const { count } = useCounts();
</script>
