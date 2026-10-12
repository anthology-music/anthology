<template>
  <span class="job-status" :data-status="status">
    <q-icon :name="statusIcons[status]" size="18px" aria-hidden="true" />
    <span class="job-status__text">{{ t(`jobs.status.${status}`) }}</span>
  </span>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import { statusIcons, type JobStatus } from '../jobs';

defineProps<{ status: JobStatus }>();
const { t } = useI18n();
</script>

<style scoped>
.job-status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  white-space: nowrap;
}

.job-status[data-status='running'] {
  color: var(--color-status-running);
}

.job-status[data-status='done'] {
  color: var(--color-status-ok);
}

.job-status[data-status='failed'] {
  color: var(--color-status-error);
}

.job-status[data-status='queued'],
.job-status[data-status='paused'],
.job-status[data-status='cancelled'] {
  color: var(--color-status-waiting);
}
</style>
