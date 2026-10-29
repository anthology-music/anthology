<template>
  <router-link
    :to="{ name: 'library-release', params: { releaseId: release.id } }"
    class="library-row"
    :data-testid="`release-${release.id}`"
  >
    <CoverImage
      :image-id="release.cover"
      :title="release.title"
      :artist="release.album_artist"
      :px="40"
      :testid="`album-cover-${release.id}`"
    />
    <span class="item-list__main">
      <span class="library-row__title">{{ release.title }}</span>
      <span class="text-muted item-list__sub library-row__title">{{ subtitle }}</span>
    </span>
    <span class="mono text-muted">{{ release.year ?? '' }}</span>
  </router-link>
</template>

<script setup lang="ts">
import type { LibraryReleaseRow } from '@anthology/api-types';
import { computed } from 'vue';

import CoverImage from '@/features/covers/components/CoverImage.vue';

const props = defineProps<{ release: LibraryReleaseRow; showArtist?: boolean }>();

const subtitle = computed(() =>
  [props.showArtist ? props.release.album_artist : null, props.release.edition]
    .filter(Boolean)
    .join(' · '),
);
</script>
