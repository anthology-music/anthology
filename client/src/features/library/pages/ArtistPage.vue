<template>
  <section class="library-section">
    <LibraryBreadcrumb
      :items="[
        { label: t('library.title'), to: { name: 'library-artists' } },
        { label: artist?.name ?? '…' },
      ]"
    />
    <MissingEntry
      v-if="state === 'missing' || state === 'removed'"
      :message="t(`library.${state}.artist`)"
    />
    <template v-else>
      <header class="library-header">
        <div class="library-header__cover" aria-hidden="true">
          <q-icon name="person" size="48px" />
        </div>
        <div class="library-header__text">
          <span class="text-muted library-header__kind">{{ t('library.artist') }}</span>
          <h1 class="library-header__title" data-testid="artist-name">{{ artist?.name ?? '…' }}</h1>
          <p v-if="artist" class="text-muted library-header__meta" data-testid="artist-counts">
            {{ count('releases', artist.release_count) }} ·
            {{ count('tracks', artist.track_count) }}
          </p>
        </div>
      </header>
      <LibraryList
        stream="library.artist.releases"
        :params="{ artist_id: artistId }"
        :position-key="`library-artist:${artistId}`"
        :label="t('library.releasesOf', { name: artist?.name ?? '' })"
        :empty="t('library.empty.artistReleases')"
      >
        <template #default="{ row }">
          <ReleaseRow :release="row as unknown as LibraryReleaseRow" />
        </template>
      </LibraryList>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { LibraryArtistRow, LibraryReleaseRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import LibraryBreadcrumb from '../components/LibraryBreadcrumb.vue';
import LibraryList from '../components/LibraryList.vue';
import MissingEntry from '../components/MissingEntry.vue';
import ReleaseRow from '../components/ReleaseRow.vue';
import { useEntry } from '../entry';
import { useCounts } from '../numbers';

const props = defineProps<{ artistId: string }>();

const { t } = useI18n();
const { count } = useCounts();
const { entry: artist, state } = useEntry<LibraryArtistRow>('library.artist', {
  artist_id: props.artistId,
});
</script>
