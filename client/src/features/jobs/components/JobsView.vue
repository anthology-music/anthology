<template>
  <div class="jobs">
    <JobCounters :total="subscription.total" :counters="subscription.counters" />

    <div class="jobs__header">
      <h2 class="settings-section__title">{{ t('jobs.title') }}</h2>
      <q-btn
        v-if="demoAvailable"
        outline
        no-caps
        icon="science"
        :label="t('jobs.startDemo')"
        :loading="startingDemo"
        data-testid="start-demo-job"
        @click="startDemo"
      />
    </div>

    <p v-if="error" class="form-error" role="alert">
      <q-icon name="info" aria-hidden="true" />{{ t(`jobs.errors.${error}`) }}
    </p>
    <p v-if="subscription.total === 0" class="text-muted" data-testid="jobs-empty">
      {{ t('jobs.empty') }}
    </p>
    <div v-else class="jobs__list">
      <VirtualList :subscription="subscription" :label="t('jobs.title')">
        <template #default="{ row }">
          <JobRow
            :job="job(row)"
            :expanded="expanded?.id === row.id"
            @toggle="toggle(job(row))"
            @control="(action) => control(job(row), action)"
          />
        </template>
      </VirtualList>
    </div>

    <JobItems v-if="expanded" :key="expanded.id" :job-id="expanded.id" :title="expanded.title" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { useAuthStore } from '@/features/users/store';
import { getServices } from '@/services';
import type { Row } from '@/sync/subscription';
import { useSubscription } from '@/sync/useSubscription';

import type { JobAction, JobRow as JobRowData } from '../jobs';
import JobCounters from './JobCounters.vue';
import JobItems from './JobItems.vue';
import JobRow from './JobRow.vue';

type ErrorCode = 'forbidden' | 'invalid_transition' | 'demo_unavailable' | 'failed';

const { t } = useI18n();
const auth = useAuthStore();
const subscription = useSubscription('jobs', {}, [0, 100]);
const expanded = ref<{ id: string; title: string } | null>(null);
const error = ref<ErrorCode | null>(null);
const startingDemo = ref(false);
const job = (row: Row) => row as unknown as JobRowData;

// Developer builds only; the server additionally needs ANTHOLOGY_DEV_DEMO=true.
// Listeners cannot start jobs.
const demoAvailable = computed(
  () => import.meta.env.DEV && auth.signedIn && auth.user?.role !== 'listener',
);

function toggle(job: JobRowData): void {
  expanded.value = expanded.value?.id === job.id ? null : { id: job.id, title: job.title };
}

function errorCode(failed: unknown): ErrorCode {
  const detail = (failed as { detail?: unknown } | undefined)?.detail;
  return detail === 'forbidden' || detail === 'invalid_transition' ? detail : 'failed';
}

async function control(job: JobRowData, action: JobAction): Promise<void> {
  error.value = null;
  const { api } = getServices();
  const options = { params: { path: { job_id: job.id } } };
  const { error: failed } =
    action === 'pause'
      ? await api.POST('/api/v1/jobs/{job_id}/pause', options)
      : action === 'resume'
        ? await api.POST('/api/v1/jobs/{job_id}/resume', options)
        : await api.POST('/api/v1/jobs/{job_id}/cancel', options);
  if (failed) error.value = errorCode(failed);
}

async function startDemo(): Promise<void> {
  error.value = null;
  startingDemo.value = true;
  try {
    const { error: failed, response } = await getServices().api.POST('/api/v1/dev/jobs/demo', {
      body: { items: 12, seconds_per_item: 1, parallel_items: 1 },
    });
    if (failed) error.value = response.status === 404 ? 'demo_unavailable' : errorCode(failed);
  } finally {
    startingDemo.value = false;
  }
}
</script>

<style scoped>
.jobs__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

/* The list needs a bounded height (it scrolls inside). */
.jobs__list {
  height: min(50vh, 520px);
  min-height: 260px;
}
</style>
