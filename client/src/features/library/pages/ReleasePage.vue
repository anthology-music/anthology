<template>
  <section class="library-section">
    <LibraryBreadcrumb
      :items="[
        { label: t('library.title'), to: { name: 'library-albums' } },
        ...(release
          ? [
              {
                label: release.album_artist,
                to: { name: 'library-artist', params: { artistId: release.album_artist_id } },
              },
            ]
          : []),
        { label: release?.title ?? '…' },
      ]"
    />
    <MissingEntry
      v-if="state === 'missing' || state === 'removed'"
      :message="t(`library.${state}.release`)"
    />
    <template v-else>
      <header class="library-header">
        <div class="library-header__cover" aria-hidden="true">
          <q-icon name="album" size="48px" />
        </div>
        <div class="library-header__text">
          <span class="text-muted library-header__kind">
            {{ t('library.album') }}<template v-if="release?.year"> · {{ release.year }}</template>
          </span>
          <h1 class="library-header__title" data-testid="release-title">
            {{ release?.title ?? '…' }}
          </h1>
          <p v-if="release" class="library-header__meta" data-testid="release-meta">
            <router-link
              :to="{ name: 'library-artist', params: { artistId: release.album_artist_id } }"
              data-testid="release-artist"
            >
              {{ release.album_artist }}
            </router-link>
            <span class="text-muted"> · {{ extent }}</span>
          </p>
          <p v-if="release?.edition" class="text-muted library-header__meta">
            {{ release.edition }}
          </p>
        </div>
      </header>
      <LibraryList
        stream="library.release.tracks"
        :params="{ release_id: releaseId }"
        :position-key="`library-release:${releaseId}`"
        :label="t('library.tracksOf', { title: release?.title ?? '' })"
        :empty="t('library.empty.releaseTracks')"
      >
        <template #default="{ row }">
          <TrackRow
            :track="row as unknown as LibraryTrackRow"
            context="release"
            :disc-count="release?.disc_count ?? 1"
          />
        </template>
      </LibraryList>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { LibraryReleaseRow, LibraryTrackRow } from '@anthology/api-types';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import LibraryBreadcrumb from '../components/LibraryBreadcrumb.vue';
import LibraryList from '../components/LibraryList.vue';
import MissingEntry from '../components/MissingEntry.vue';
import TrackRow from '../components/TrackRow.vue';
import { useEntry } from '../entry';
import { useCounts } from '../numbers';

const props = defineProps<{ releaseId: string }>();

const { t } = useI18n();
const { count } = useCounts();
const { entry: release, state } = useEntry<LibraryReleaseRow>('library.release', {
  release_id: props.releaseId,
});

const extent = computed(() =>
  release.value
    ? [
        count('tracks', release.value.track_count),
        ...(release.value.disc_count > 1 ? [count('discs', release.value.disc_count)] : []),
      ].join(' · ')
    : '',
);
</script>
