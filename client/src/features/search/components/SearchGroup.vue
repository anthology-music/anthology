<template>
  <section class="search-group" :data-testid="`search-group-${type}`">
    <header class="search-group__header">
      <h2 class="search-group__title">
        {{ t(`search.types.${type}`) }}
        <span class="mono text-muted" :data-testid="`search-count-${type}`">{{ shown }}</span>
      </h2>
      <router-link
        v-if="(subscription.total ?? 0) > PREVIEW"
        :to="{ name: 'search', query: { ...route.query, type } }"
        :data-testid="`search-all-${type}`"
      >
        {{ t('search.showAll') }}
      </router-link>
    </header>
    <p v-if="subscription.total === 0" class="text-muted">{{ t('search.none') }}</p>
    <ul v-else class="search-group__rows">
      <li v-for="row in rows" :key="String(row.id)">
        <SearchRow :type="type" :row="row" :rule="playRule" />
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

import { useSubscription } from '@/sync/useSubscription';

import { type ItemType, STREAMS } from '../query';
import { useResultCount } from '../count';
import SearchRow from './SearchRow.vue';

/** One result type of the overview: its count first, then its first rows. */
const props = defineProps<{ type: ItemType; params: Record<string, unknown> }>();

const PREVIEW = 5;
const { t } = useI18n();
const route = useRoute();
const subscription = useSubscription(STREAMS[props.type], props.params, [0, PREVIEW], {
  cache: false,
});
const shown = useResultCount(subscription);
// Playing a track plays the search results from it.
const playRule = {
  list: 'search' as const,
  q: (props.params.q as string | undefined) ?? '',
  release_id: (props.params.release_id as string | undefined) ?? null,
  artist_id: (props.params.artist_id as string | undefined) ?? null,
};
const rows = computed(() =>
  [...Array(Math.min(PREVIEW, subscription.value.total ?? 0)).keys()]
    .map((position) => subscription.value.rows.get(position))
    .filter((row) => row !== undefined),
);
</script>

<style scoped>
.search-group {
  margin-bottom: var(--space-5);
}

.search-group__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.search-group__title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-lg);
  font-weight: var(--weight-medium);
}

.search-group__rows {
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
