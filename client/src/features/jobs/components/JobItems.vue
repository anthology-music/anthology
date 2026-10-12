<template>
  <section class="job-items" :aria-label="t('jobs.itemsOf', { title })" data-testid="job-items">
    <h3 class="settings-section__title">
      {{ t('jobs.itemsOf', { title }) }}
      <span class="text-muted mono">{{ subscription.total ?? '…' }}</span>
    </h3>
    <div class="job-items__list">
      <VirtualList :subscription="subscription" :label="t('jobs.itemsOf', { title })">
        <template #default="{ row, position }">
          <span class="mono text-muted job-items__position">{{ position + 1 }}</span>
          <div class="item-list__main">
            <span>{{ item(row).title }}</span>
            <span v-if="item(row).message" class="text-muted item-list__sub">
              {{ item(row).message }}
            </span>
          </div>
          <ProgressBar
            class="job-items__progress"
            :value="percent(item(row).progress)"
            :label="t('jobs.progressOf', { title: item(row).title })"
          />
          <JobStatusLabel :status="item(row).status" />
        </template>
      </VirtualList>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import type { Row } from '@/sync/subscription';
import { useSubscription } from '@/sync/useSubscription';

import { percent, type JobItemRow } from '../jobs';
import JobStatusLabel from './JobStatusLabel.vue';
import ProgressBar from './ProgressBar.vue';

const props = defineProps<{ jobId: string; title: string }>();
const { t } = useI18n();
// Remounted per job (keyed by the parent), so the parameters stay fixed.
const subscription = useSubscription('job.items', { job_id: props.jobId }, [0, 100]);
const item = (row: Row) => row as unknown as JobItemRow;
</script>

<style scoped>
.job-items {
  margin-top: var(--space-6);
}

.job-items__list {
  height: min(40vh, 420px);
  min-height: 200px;
}

.job-items__position {
  min-width: 5ch;
  text-align: right;
  margin-right: var(--space-3);
}

.job-items__progress {
  width: 160px;
  margin: 0 var(--space-4);
}
</style>
