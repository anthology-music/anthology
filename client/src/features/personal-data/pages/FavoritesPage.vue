<template>
  <section class="library-section">
    <h1 class="library-section__title">{{ t('personal.favorites.title') }}</h1>
    <LibraryList
      stream="personal.favorites"
      position-key="favorites"
      :label="t('personal.favorites.title')"
      :empty="t('personal.favorites.empty')"
      uncached
    >
      <template #default="{ row }">
        <router-link
          :to="target(row as unknown as FavoriteRow)"
          class="library-row"
          :data-testid="`favorite-row-${(row as unknown as FavoriteRow).target_id}`"
        >
          <q-icon :name="ICONS[(row as unknown as FavoriteRow).target_type]" aria-hidden="true" />
          <span class="item-list__main">
            <span class="library-row__title">{{ row.label }}</span>
            <span class="text-muted item-list__sub">
              {{ t(`personal.favorites.kinds.${(row as unknown as FavoriteRow).target_type}`) }}
            </span>
          </span>
          <FavoriteButton
            :id="(row as unknown as FavoriteRow).target_id"
            :type="(row as unknown as FavoriteRow).target_type"
            :name="String(row.label)"
            size="sm"
          />
        </router-link>
      </template>
    </LibraryList>
  </section>
</template>

<script setup lang="ts">
import type { FavoriteRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';
import type { RouteLocationRaw } from 'vue-router';

import LibraryList from '@/features/library/components/LibraryList.vue';

import FavoriteButton from '../components/FavoriteButton.vue';

/** The user's favorites (private, spec: personal-data, Favorites). */
const { t } = useI18n();
const ICONS = { recording: 'music_note', release: 'album', artist: 'person' } as const;

function target(row: FavoriteRow): RouteLocationRaw {
  if (row.target_type === 'release')
    return { name: 'library-release', params: { releaseId: row.target_id } };
  if (row.target_type === 'artist')
    return { name: 'library-artist', params: { artistId: row.target_id } };
  return { name: 'search', query: { q: row.label } };
}
</script>
