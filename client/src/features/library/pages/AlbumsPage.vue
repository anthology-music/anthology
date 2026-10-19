<template>
  <section class="library-section">
    <h1 class="library-section__title">{{ t('library.sections.releases') }}</h1>
    <LibraryList
      stream="library.releases"
      position-key="library-albums"
      :label="t('library.sections.releases')"
      :empty="t('library.empty.releases')"
    >
      <template #default="{ row }">
        <ReleaseRow :release="row as unknown as LibraryReleaseRow" show-artist />
      </template>
    </LibraryList>
  </section>
</template>

<script setup lang="ts">
import type { LibraryReleaseRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import LibraryList from '../components/LibraryList.vue';
import ReleaseRow from '../components/ReleaseRow.vue';

const { t } = useI18n();
</script>
