<template>
  <p v-if="subscription.total === 0" class="text-muted">{{ t('search.none') }}</p>
  <ul v-else class="picker-results">
    <li v-for="row in rows" :key="String(row.id)">
      <button
        type="button"
        class="picker-results__row"
        :data-testid="`${testid}-${String(row.title)}`"
        @click="emit('pick', row)"
      >
        <span>{{ row.title }}</span>
        <span class="text-muted picker-results__sub">{{ subtitle(row) }}</span>
      </button>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { useSubscription } from '@/sync/useSubscription';

/** The first results of one search, as buttons. */
const props = defineProps<{ stream: string; q: string; testid: string }>();
const emit = defineEmits<{ pick: [row: Record<string, unknown>] }>();
const LIMIT = 10;
const { t } = useI18n();
const subscription = useSubscription(props.stream, { q: props.q }, [0, LIMIT], { cache: false });
const rows = computed(() =>
  [...Array(Math.min(LIMIT, subscription.value.total ?? 0)).keys()]
    .map((position) => subscription.value.rows.get(position))
    .filter((row) => row !== undefined),
);

function subtitle(row: Record<string, unknown>): string {
  if (props.stream === 'search.tracks') return `${String(row.artist)} · ${String(row.album)}`;
  const type = t(`works.types.${String(row.type)}`);
  const composers = (row.composers as string[] | undefined) ?? [];
  return composers.length ? `${type} · ${composers.join(', ')}` : type;
}
</script>

<style scoped>
.picker-results {
  margin: var(--space-2) 0 0;
  padding: 0;
  list-style: none;
}

.picker-results__row {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: var(--touch-target);
  padding: var(--space-1) var(--space-2);
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.picker-results__row:hover,
.picker-results__row:focus-visible {
  background: var(--color-surface-raised);
}

.picker-results__sub {
  font-size: var(--text-sm);
}
</style>
