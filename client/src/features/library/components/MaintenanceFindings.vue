<template>
  <div class="findings" data-testid="maintenance-findings">
    <VirtualList :subscription="subscription" :label="t('maintenance.findings')">
      <template #default="{ row }">
        <div class="finding-row" :data-testid="`finding-${row.id}`">
          <span class="badge">{{ t(`maintenance.kinds.${finding(row).kind}`) }}</span>
          <span class="item-list__main">
            <span class="mono finding-row__path">{{ finding(row).path }}</span>
            <span
              v-if="finding(row).outcome"
              class="text-muted item-list__sub"
              :data-testid="`finding-outcome-${row.id}`"
            >
              {{ t(`maintenance.outcomes.${finding(row).outcome}`) }}
            </span>
          </span>
          <span class="mono text-muted">{{ formatSize(finding(row).size_bytes, locale) }}</span>
        </div>
      </template>
    </VirtualList>
  </div>
</template>

<script setup lang="ts">
import type { MaintenanceFindingRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import type { Row } from '@/sync/subscription';
import { useSubscription } from '@/sync/useSubscription';

import { formatSize } from '../numbers';

const props = defineProps<{ runId: string }>();

const { t, locale } = useI18n();
const subscription = useSubscription(
  'library.maintenance.findings',
  { run_id: props.runId },
  [0, 50],
);
const finding = (row: Row) => row as unknown as MaintenanceFindingRow;
</script>

<style scoped>
/* The list needs a bounded height (it scrolls inside). */
.findings {
  height: min(30vh, 320px);
  min-height: 160px;
  margin-top: var(--space-3);
}

.finding-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 100%;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-divider);
}

.finding-row__path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
