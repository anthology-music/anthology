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
          <q-btn
            v-if="release && release.track_count"
            unelevated
            rounded
            no-caps
            color="primary"
            icon="play_arrow"
            :label="t('playback.playAlbum')"
            class="library-header__play"
            data-testid="play-release"
            @click="player.playList(listRule)"
          />
          <q-btn
            v-if="release && release.track_count"
            outline
            rounded
            no-caps
            icon="download"
            :label="t('library.download.release')"
            :loading="downloads.busy"
            class="library-header__play"
            data-testid="download-release"
            @click="downloads.downloadRelease(releaseId)"
          />
          <router-link
            v-if="release"
            :to="{ name: 'search', query: { q: '', release_id: releaseId, in: release.title } }"
            data-testid="search-in-release"
          >
            <q-icon name="search" aria-hidden="true" /> {{ t('search.inRelease') }}
          </router-link>
        </div>
        <div v-if="auth.canEdit" class="library-header__actions">
          <EditModeSwitch v-model="editing" />
          <q-btn
            v-if="editing && release"
            outline
            no-caps
            :label="t('tagging.editRelease')"
            data-testid="edit-release"
            @click="editingRelease = true"
          />
        </div>
      </header>
      <EditBar v-if="editing" :selection="selection" />
      <TagEditor
        v-if="release"
        :open="editingRelease"
        :selection="{ rule: listRule }"
        :count="release.track_count"
        mode="release"
        @close="editingRelease = false"
      />
      <LibraryList
        ref="list"
        stream="library.release.tracks"
        :params="{ release_id: releaseId }"
        :position-key="`library-release:${releaseId}`"
        :label="t('library.tracksOf', { title: release?.title ?? '' })"
        :empty="t('library.empty.releaseTracks')"
      >
        <template #default="{ row, position, rowAt }">
          <SelectableRow
            v-if="editing"
            :id="String(row.id)"
            :selected="selection.selected(String(row.id))"
            :label="t('tagging.select', { name: String(row.title) })"
            @toggle="
              (shift) =>
                selection.toggle(
                  String(row.id),
                  position,
                  shift,
                  (p) => rowAt(p) as { id: string } | undefined,
                )
            "
          >
            <TrackRow
              :track="row as unknown as LibraryTrackRow"
              context="release"
              :disc-count="release?.disc_count ?? 1"
            />
          </SelectableRow>
          <PlayableTrackRow
            v-else
            :track="row as unknown as LibraryTrackRow"
            context="release"
            :rule="listRule"
            :disc-count="release?.disc_count ?? 1"
          />
        </template>
      </LibraryList>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { LibraryReleaseRow, LibraryTrackRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import PlayableTrackRow from '@/features/playback/components/PlayableTrackRow.vue';
import { usePlayerStore } from '@/features/playback/store';
import EditBar from '@/features/tagging/components/EditBar.vue';
import EditModeSwitch from '@/features/tagging/components/EditModeSwitch.vue';
import SelectableRow from '@/features/tagging/components/SelectableRow.vue';
import TagEditor from '@/features/tagging/components/TagEditor.vue';
import { type EditRule, useSelection } from '@/features/tagging/selection';
import { useAuthStore } from '@/features/users/store';

import LibraryBreadcrumb from '../components/LibraryBreadcrumb.vue';
import LibraryList from '../components/LibraryList.vue';
import MissingEntry from '../components/MissingEntry.vue';
import TrackRow from '../components/TrackRow.vue';
import { useDownloadStore } from '../downloads';
import { useEntry } from '../entry';
import { useCounts } from '../numbers';

const props = defineProps<{ releaseId: string }>();

const { t } = useI18n();
const { count } = useCounts();
const { entry: release, state } = useEntry<LibraryReleaseRow>('library.release', {
  release_id: props.releaseId,
});

const auth = useAuthStore();
const downloads = useDownloadStore();
const player = usePlayerStore();
const editing = ref(false);
const editingRelease = ref(false);
const list = ref<InstanceType<typeof LibraryList> | null>(null);
const listRule: EditRule = { list: 'release_tracks', release_id: props.releaseId };
const selection = useSelection(
  () => listRule,
  () => list.value?.total() ?? null,
);

const extent = computed(() =>
  release.value
    ? [
        count('tracks', release.value.track_count),
        ...(release.value.disc_count > 1 ? [count('discs', release.value.disc_count)] : []),
      ].join(' · ')
    : '',
);
</script>
