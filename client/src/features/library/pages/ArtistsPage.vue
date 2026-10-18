<template>
  <section class="library-section">
    <h1 class="library-section__title">{{ t('library.sections.artists') }}</h1>
    <LibraryList
      stream="library.artists"
      position-key="library-artists"
      :label="t('library.sections.artists')"
      :empty="t('library.empty.artists')"
    >
      <template #default="{ row }">
        <ArtistRow :artist="row as unknown as LibraryArtistRow" />
      </template>
    </LibraryList>
  </section>
</template>

<script setup lang="ts">
import type { LibraryArtistRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import ArtistRow from '../components/ArtistRow.vue';
import LibraryList from '../components/LibraryList.vue';

const { t } = useI18n();
</script>
