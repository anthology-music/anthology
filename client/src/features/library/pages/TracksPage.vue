<template>
  <section class="library-section">
    <h1 class="library-section__title">{{ t('library.sections.tracks') }}</h1>
    <LibraryList
      stream="library.tracks"
      position-key="library-tracks"
      :label="t('library.sections.tracks')"
      :empty="t('library.empty.tracks')"
    >
      <template #default="{ row }">
        <TrackRow :track="row as unknown as LibraryTrackRow" context="library" />
      </template>
    </LibraryList>
  </section>
</template>

<script setup lang="ts">
import type { LibraryTrackRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import LibraryList from '../components/LibraryList.vue';
import TrackRow from '../components/TrackRow.vue';

const { t } = useI18n();
</script>
