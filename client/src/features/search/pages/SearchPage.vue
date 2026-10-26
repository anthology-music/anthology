<template>
  <section class="library-section search-page">
    <h1 class="library-section__title">{{ t('search.title') }}</h1>

    <div class="search-page__chips" data-testid="search-chips">
      <q-chip
        v-if="hasContext"
        removable
        icon="filter_center_focus"
        data-testid="search-context"
        :label="t('search.context', { name: context.label ?? '…' })"
        @remove="removeContext"
      />
      <q-chip
        v-for="token in filters"
        :key="`${token.start}-${token.text}`"
        removable
        :data-testid="`search-chip-${token.field}`"
        :label="`${fieldLabel(token.field)}: ${token.op === '=' ? '' : token.op}${token.value}`"
        @remove="setText(removeToken(q, token))"
      />
      <q-btn
        flat
        no-caps
        icon="add"
        :label="t('search.addFilter')"
        :aria-expanded="adding"
        data-testid="search-add-filter"
        @click="adding = !adding"
      />
    </div>
    <form v-if="adding" class="search-page__add" @submit.prevent="addFilter">
      <q-select
        v-model="newField"
        dense
        outlined
        emit-value
        map-options
        :options="fieldOptions"
        :label="t('search.field')"
        data-testid="search-filter-field"
      />
      <q-input
        v-model="newValue"
        dense
        outlined
        autofocus
        :label="t('search.value')"
        data-testid="search-filter-value"
      />
      <q-btn
        type="submit"
        unelevated
        no-caps
        color="primary"
        :label="t('search.add')"
        data-testid="search-filter-add"
      />
    </form>
    <ul v-if="errors.length" class="search-page__hints" data-testid="search-hints">
      <li v-for="token in errors" :key="`${token.start}-${token.text}`">
        <q-icon name="info" aria-hidden="true" />
        {{ t(`search.errors.${token.error}`, { field: token.field ?? '', text: token.text }) }}
      </li>
    </ul>

    <p v-if="!q" class="text-muted" data-testid="search-start">{{ t('search.start') }}</p>
    <template v-else-if="type">
      <div class="search-page__list-header">
        <router-link :to="{ name: 'search', query: { ...route.query, type: undefined } }">
          {{ t('search.allTypes') }}
        </router-link>
        <h2 class="search-page__list-title">
          {{ t(`search.types.${type}`) }}
          <span class="mono text-muted" data-testid="search-list-count">{{ listCount }}</span>
        </h2>
        <q-btn
          v-if="type === 'track' && auth.canEdit && listTotal"
          unelevated
          no-caps
          color="primary"
          :label="t('search.editAll')"
          data-testid="search-edit-all"
          @click="editing = true"
        />
      </div>
      <p v-if="capped" class="text-muted" data-testid="search-capped">{{ t('search.capped') }}</p>
      <p v-if="message" role="status" data-testid="search-message">{{ message }}</p>
      <LibraryList
        ref="list"
        :key="paramsKey"
        :stream="STREAMS[type]"
        :params="params"
        :position-key="`search:${type}:${paramsKey}`"
        :label="t(`search.types.${type}`)"
        :empty="t('search.none')"
        uncached
      >
        <template #default="{ row }">
          <SearchRow :type="type" :row="row" />
        </template>
      </LibraryList>
      <TagEditor
        v-if="type === 'track'"
        :open="editing"
        :selection="{ rule: searchRule(q, context) }"
        :count="listTotal ?? 0"
        mode="tracks"
        @close="editing = false"
        @done="done"
      />
    </template>
    <div v-else :key="paramsKey" class="search-page__groups">
      <SearchGroup
        v-for="itemType in visibleTypes"
        :key="itemType"
        :type="itemType"
        :params="params"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import LibraryList from '@/features/library/components/LibraryList.vue';
import { useCounts } from '@/features/library/numbers';
import TagEditor, { type EditResult } from '@/features/tagging/components/TagEditor.vue';
import { useAuthStore } from '@/features/users/store';
import { getServices } from '@/services';

import SearchGroup from '../components/SearchGroup.vue';
import SearchRow from '../components/SearchRow.vue';
import {
  appendFilter,
  FILTER_FIELDS,
  type ItemType,
  removeToken,
  type SearchContext,
  type SearchToken,
  searchParams,
  searchRule,
  STREAMS,
} from '../query';

/** Search results grouped by type, or the full list of one type (spec: search). The text,
 * the type and the context live in the address; the server parses the text into chips. */
const { t } = useI18n();
const { number } = useCounts();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const q = computed(() => String(route.query.q ?? '').trim());
const type = computed(() => {
  const value = String(route.query.type ?? '');
  return value in STREAMS ? (value as ItemType) : null;
});
const context = computed<SearchContext>(() => ({
  release_id: route.query.release_id ? String(route.query.release_id) : undefined,
  artist_id: route.query.artist_id ? String(route.query.artist_id) : undefined,
  label: route.query.in ? String(route.query.in) : undefined,
}));
const hasContext = computed(() => Boolean(context.value.release_id || context.value.artist_id));
const params = computed(() => searchParams(q.value, context.value));
const paramsKey = computed(() => JSON.stringify(params.value));

// --- tokens and chips ---------------------------------------------------------------------

const tokens = ref<SearchToken[]>([]);
const allowed = ref<ItemType[]>(['artist', 'release', 'track']);
const filters = computed(() =>
  tokens.value.filter((token) => token.kind === 'filter' && !token.error),
);
const errors = computed(() => tokens.value.filter((token) => token.error));
const visibleTypes = computed(() =>
  (['artist', 'release', 'track'] as const).filter(
    (itemType) =>
      allowed.value.includes(itemType) &&
      (!context.value.release_id || itemType === 'track') &&
      (!context.value.artist_id || itemType !== 'artist'),
  ),
);

watch(
  q,
  async (text) => {
    if (!text) {
      tokens.value = [];
      allowed.value = ['artist', 'release', 'track'];
      return;
    }
    const { data } = await getServices().api.GET('/api/v1/search/parse', {
      params: { query: { q: text } },
    });
    if (data && text === q.value) {
      tokens.value = data.tokens;
      allowed.value = data.types;
    }
  },
  { immediate: true },
);

const fieldLabel = (field: string | null | undefined) => t(`search.fields.${field ?? ''}`);
const fieldOptions = FILTER_FIELDS.map((field) => ({ value: field, label: fieldLabel(field) }));
const adding = ref(false);
const newField = ref<string>('genre');
const newValue = ref('');

function setText(text: string): void {
  void router.replace({ name: 'search', query: { ...route.query, q: text } });
}

function addFilter(): void {
  setText(appendFilter(q.value, newField.value, newValue.value));
  newValue.value = '';
  adding.value = false;
}

function removeContext(): void {
  const query = { ...route.query };
  for (const name of ['release_id', 'artist_id', 'in']) delete query[name];
  void router.replace({ name: 'search', query });
}

// --- full list and editing ----------------------------------------------------------------

const list = ref<InstanceType<typeof LibraryList> | null>(null);
const listTotal = computed(() => list.value?.subscription.total ?? null);
const capped = computed(() => Boolean(list.value?.subscription.counters.capped));
const listCount = computed(() => `${number(listTotal.value)}${capped.value ? '+' : ''}`);
const editing = ref(false);
const message = ref<string | null>(null);

function done(result: EditResult): void {
  message.value =
    result.kind === 'job'
      ? t('tagging.result.job', { n: number(result.items) }, result.items)
      : t('tagging.result.saved', { n: number(result.changed) }, result.changed);
}
</script>

<style scoped>
.search-page__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.search-page__add {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.search-page__add > :not(button) {
  flex: 1 1 180px;
}

.search-page__hints {
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
  color: var(--color-text-secondary);
}

.search-page__list-header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.search-page__list-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--weight-medium);
}
</style>
