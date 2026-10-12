<template>
  <div class="job-row" :data-testid="`job-${job.id}`">
    <button
      type="button"
      class="job-row__title"
      :aria-expanded="expanded"
      :aria-label="t(expanded ? 'jobs.hideItems' : 'jobs.showItems', { title: job.title })"
      @click="emit('toggle')"
    >
      <q-icon :name="expanded ? 'expand_less' : 'expand_more'" size="20px" aria-hidden="true" />
      <span class="item-list__main">
        <span class="job-row__name">{{ job.title }}</span>
        <span class="text-muted item-list__sub">
          {{ t('jobs.by', { name: job.created_by_name }) }}
          <template v-if="job.error"> · {{ job.error }}</template>
        </span>
      </span>
    </button>
    <span class="job-row__count mono" data-testid="job-count">
      {{ job.done_items + job.failed_items }} / {{ job.total_items }}
    </span>
    <ProgressBar
      class="job-row__progress"
      :value="percent(job.progress)"
      :label="t('jobs.progressOf', { title: job.title })"
    />
    <JobStatusLabel class="job-row__status" :status="job.status" />
    <span class="job-row__actions">
      <template v-if="controllable">
        <q-btn
          v-for="action in actionsFor(job.status)"
          :key="action"
          flat
          round
          size="sm"
          :icon="actionIcons[action]"
          :aria-label="t(`jobs.actions.${action}`, { title: job.title })"
          :title="t(`jobs.actions.${action}`, { title: job.title })"
          :data-testid="`job-${action}`"
          @click="emit('control', action)"
        />
      </template>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { useAuthStore } from '@/features/users/store';

import { actionsFor, canControl, percent, type JobAction, type JobRow } from '../jobs';
import JobStatusLabel from './JobStatusLabel.vue';
import ProgressBar from './ProgressBar.vue';

const props = defineProps<{ job: JobRow; expanded: boolean }>();
const emit = defineEmits<{ toggle: []; control: [action: JobAction] }>();
const { t } = useI18n();
const auth = useAuthStore();

const actionIcons: Record<JobAction, string> = {
  pause: 'pause',
  resume: 'play_arrow',
  cancel: 'close',
};

const controllable = computed(() => canControl(props.job, auth.user));
</script>

<style scoped>
.job-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 9ch minmax(100px, 180px) 14ch calc(2 * var(--touch-target));
  align-items: center;
  gap: var(--space-4);
  width: 100%;
  padding: 0 var(--space-3);
}

.job-row__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  min-height: var(--touch-target);
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.job-row__name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.job-row__count {
  text-align: right;
  font-size: var(--text-sm);
}

.job-row__actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 599px) {
  .job-row {
    grid-template-columns: minmax(0, 1fr) auto calc(2 * var(--touch-target));
  }

  .job-row__count,
  .job-row__progress {
    display: none;
  }
}
</style>
