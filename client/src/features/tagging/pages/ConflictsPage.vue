<template>
  <q-page class="page">
    <PageHeader :title="t('conflicts.title')" :description="t('conflicts.description')" />
    <div class="conflicts-page">
      <aside class="conflicts-page__groups" :aria-label="t('conflicts.groups')">
        <label class="conflicts-page__by">
          {{ t('conflicts.groupBy') }}
          <select v-model="by" data-testid="conflicts-group-by" @change="select(null)">
            <option v-for="option in BY" :key="option" :value="option">
              {{ t(`conflicts.by.${option}`) }}
            </option>
          </select>
        </label>
        <button
          type="button"
          class="conflicts-page__group"
          :aria-pressed="group === null"
          data-testid="group-all"
          @click="select(null)"
        >
          {{ t('conflicts.all') }}
        </button>
        <button
          v-for="item in groups"
          :key="item.value"
          type="button"
          class="conflicts-page__group"
          :aria-pressed="group?.value === item.value"
          :data-testid="`group-${item.value}`"
          @click="select(item.value)"
        >
          <span>{{ groupLabel(item) }}</span>
          <span class="badge">{{ number(item.count) }}</span>
        </button>
      </aside>
      <ConflictView :key="key" :group="group" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';
import { useCounts } from '@/features/library/numbers';
import { getServices } from '@/services';

import ConflictView from '../components/ConflictView.vue';
import type { ConflictGroup } from '../conflicts';

type By = 'release' | 'artist' | 'field' | 'source';
const BY: By[] = ['release', 'artist', 'field', 'source'];
const PARAMS: Record<By, ConflictGroup['param']> = {
  release: 'release_id',
  artist: 'artist_id',
  field: 'field',
  source: 'source',
};
// The groups follow decisions with a short delay.
const REFRESH_MS = 3_000;

/** The conflict list (spec: tagging, Conflict list): groups with counts, then the entries. */
const { t } = useI18n();
const { number } = useCounts();
const by = ref<By>('release');
const groups = ref<Schemas['ConflictGroup'][]>([]);
const group = ref<ConflictGroup | null>(null);
const key = computed(() => JSON.stringify(group.value));
let timer: ReturnType<typeof setInterval> | null = null;

function groupLabel(item: Schemas['ConflictGroup']): string {
  if (by.value === 'field') return t(`tagging.fields.${item.value}`);
  if (by.value === 'source') return t(`review.origins.${item.value}`);
  return item.label;
}

async function load(): Promise<void> {
  const { data } = await getServices().api.GET('/api/v1/tagging/conflicts/groups', {
    params: { query: { by: by.value } },
  });
  if (data) groups.value = data;
}

function select(value: string | null): void {
  group.value = value === null ? null : { param: PARAMS[by.value], value };
  void load();
}

onMounted(() => {
  void load();
  timer = setInterval(() => void load(), REFRESH_MS);
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.conflicts-page {
  display: grid;
  grid-template-columns: minmax(200px, 280px) minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
}

.conflicts-page__groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.conflicts-page__by {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.conflicts-page__by select {
  min-height: var(--touch-target);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.conflicts-page__group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  color: var(--color-text-secondary);
  text-align: left;
  background: none;
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.conflicts-page__group[aria-pressed='true'] {
  color: var(--color-text);
  background: var(--color-active-bg);
}

.conflicts-page__group:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

@media (max-width: 899px) {
  .conflicts-page {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
