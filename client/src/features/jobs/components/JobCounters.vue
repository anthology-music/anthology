<template>
  <section class="job-counters" :aria-label="t('jobs.overview')">
    <div v-for="tile in tiles" :key="tile.key" class="job-counters__tile" :data-status="tile.key">
      <span class="job-counters__label">{{ t(`jobs.counters.${tile.key}`) }}</span>
      <span class="job-counters__value mono" :data-testid="`job-counter-${tile.key}`">
        {{ total === null ? '…' : tile.value }}
      </span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ total: number | null; counters: Record<string, number> }>();
const { t } = useI18n();

const tiles = computed(() => [
  { key: 'total', value: props.total ?? 0 },
  { key: 'done', value: props.counters.done ?? 0 },
  { key: 'running', value: props.counters.running ?? 0 },
  { key: 'waiting', value: (props.counters.queued ?? 0) + (props.counters.paused ?? 0) },
  { key: 'failed', value: props.counters.failed ?? 0 },
]);
</script>

<style scoped>
.job-counters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.job-counters__tile {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.job-counters__label {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.job-counters__value {
  font-size: var(--text-xl);
  font-weight: var(--weight-medium);
}

[data-status='done'] .job-counters__value {
  color: var(--color-status-ok);
}

[data-status='running'] .job-counters__value {
  color: var(--color-status-running);
}

[data-status='waiting'] .job-counters__value {
  color: var(--color-status-waiting);
}

[data-status='failed'] .job-counters__value {
  color: var(--color-status-error);
}
</style>
