<template>
  <section class="settings-section" aria-labelledby="maintenance-title">
    <h2 id="maintenance-title" class="settings-section__title">{{ t('maintenance.title') }}</h2>
    <p class="text-muted maintenance__hint">{{ t('maintenance.hint') }}</p>

    <form
      v-if="form"
      class="maintenance__form"
      data-testid="maintenance-form"
      @submit.prevent="save"
    >
      <fieldset class="maintenance__group">
        <legend class="maintenance__legend">{{ t('maintenance.schedule') }}</legend>
        <label
          v-for="option in FREQUENCIES"
          :key="option"
          class="maintenance__choice"
          :data-testid="`maintenance-frequency-${option}`"
        >
          <input
            v-model="form.frequency"
            type="radio"
            name="maintenance-frequency"
            :value="option"
          />
          {{ t(`maintenance.frequencies.${option}`) }}
        </label>
        <div v-if="form.frequency !== 'off'" class="maintenance__row">
          <label v-if="form.frequency === 'weekly'" class="maintenance__field">
            {{ t('maintenance.weekday') }}
            <select v-model.number="form.weekday" data-testid="maintenance-weekday">
              <option v-for="(name, index) in weekdays" :key="index" :value="index">
                {{ name }}
              </option>
            </select>
          </label>
          <label class="maintenance__field">
            {{ t('maintenance.time') }}
            <input v-model="form.time" type="time" required data-testid="maintenance-time" />
          </label>
        </div>
      </fieldset>

      <fieldset class="maintenance__group">
        <legend class="maintenance__legend">{{ t('maintenance.action') }}</legend>
        <label
          v-for="option in ACTIONS"
          :key="option"
          class="maintenance__choice"
          :data-testid="`maintenance-action-${option}`"
        >
          <input v-model="form.action" type="radio" name="maintenance-action" :value="option" />
          {{ t(`maintenance.actions.${option}`) }}
        </label>
      </fieldset>

      <div class="maintenance__row">
        <label class="maintenance__field">
          {{ t('maintenance.grace') }}
          <input
            v-model.number="form.graceHours"
            type="number"
            min="1"
            max="168"
            step="1"
            required
            data-testid="maintenance-grace"
          />
          <span class="text-muted maintenance__note">{{ t('maintenance.graceHint') }}</span>
        </label>
      </div>

      <fieldset class="maintenance__group">
        <legend class="maintenance__legend">{{ t('maintenance.safety') }}</legend>
        <label class="maintenance__choice">
          <input v-model="form.safetyOn" type="checkbox" data-testid="maintenance-safety-on" />
          {{ t('maintenance.safetyOn') }}
        </label>
        <label v-if="form.safetyOn" class="maintenance__field">
          {{ t('maintenance.safetyShare') }}
          <input
            v-model.number="form.safetyShare"
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            required
            data-testid="maintenance-safety-share"
          />
        </label>
        <span class="text-muted maintenance__note">{{ t('maintenance.safetyHint') }}</span>
      </fieldset>

      <p class="maintenance__next" data-testid="maintenance-next">
        <q-icon name="schedule" aria-hidden="true" />
        {{
          schedule?.next_run_at
            ? t('maintenance.nextRun', {
                date: formatDate(schedule.next_run_at),
                zone: schedule.time_zone,
              })
            : t('maintenance.noNextRun')
        }}
      </p>

      <div class="maintenance__actions">
        <q-btn
          flat
          no-caps
          icon="play_arrow"
          :label="running ? t('maintenance.runActive') : t('maintenance.runNow')"
          :disable="running"
          :loading="starting"
          data-testid="maintenance-run"
          @click="runNow"
        />
        <q-btn
          unelevated
          no-caps
          color="primary"
          type="submit"
          :label="t('maintenance.save')"
          :loading="saving"
          data-testid="maintenance-save"
        />
      </div>
    </form>
    <p v-if="message" class="maintenance__message" role="status" data-testid="maintenance-message">
      <q-icon
        :name="message === 'started' || message === 'saved' ? 'check_circle' : 'info'"
        aria-hidden="true"
      />
      {{ t(`maintenance.messages.${message}`) }}
    </p>

    <h3 class="maintenance__subtitle">{{ t('maintenance.lastRun') }}</h3>
    <p v-if="!run" class="text-muted" data-testid="maintenance-no-run">
      {{ t('maintenance.noRun') }}
    </p>
    <template v-else>
      <p class="maintenance__status" data-testid="maintenance-status">
        <span class="badge">{{ t(`maintenance.statuses.${run.status}`) }}</span>
        {{ formatDate(run.finished_at ?? run.started_at) }}
        <span v-if="run.error" class="text-muted">{{ run.error }}</span>
      </p>
      <ul class="item-list">
        <li class="item-list__row" data-testid="maintenance-deleted">
          <span class="item-list__main">{{ t('maintenance.counts.deleted') }}</span>
          <span class="mono">{{ summary(run.deleted_files, run.deleted_bytes) }}</span>
        </li>
        <li class="item-list__row" data-testid="maintenance-listed">
          <span class="item-list__main">{{ t('maintenance.counts.listed') }}</span>
          <span class="mono">{{ summary(run.listed_files, run.listed_bytes) }}</span>
        </li>
        <li class="item-list__row" data-testid="maintenance-missing">
          <span class="item-list__main">{{ t('maintenance.counts.missing') }}</span>
          <span class="mono">{{ summary(run.missing_files, run.missing_bytes) }}</span>
        </li>
      </ul>

      <div v-if="run.status === 'held'" class="maintenance__held" data-testid="maintenance-held">
        <p>
          {{
            t('maintenance.heldHint', {
              files: summary(run.listed_files, run.listed_bytes),
              limit: number(run.safety_limit),
            })
          }}
        </p>
        <q-btn
          unelevated
          no-caps
          color="negative"
          icon="delete_sweep"
          :label="t('maintenance.confirmDelete')"
          :loading="confirmingRun"
          data-testid="maintenance-confirm-open"
          @click="confirming = true"
        />
      </div>

      <MaintenanceFindings
        v-if="run.orphan_files + run.leftover_files + run.missing_files > 0"
        :key="run.id"
        :run-id="run.id"
      />
    </template>

    <q-dialog v-model="confirming">
      <q-card class="maintenance__dialog" data-testid="maintenance-dialog">
        <q-card-section>
          <h3 class="settings-section__title">{{ t('maintenance.confirmTitle') }}</h3>
          <p v-if="run">
            {{
              t('maintenance.confirmText', { files: summary(run.listed_files, run.listed_bytes) })
            }}
          </p>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('maintenance.cancel')" @click="confirming = false" />
          <q-btn
            unelevated
            no-caps
            color="negative"
            :label="t('maintenance.confirm')"
            data-testid="maintenance-confirm"
            @click="confirmRun"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </section>
</template>

<script setup lang="ts">
import type { MaintenanceRunRow, Schemas } from '@anthology/api-types';
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

import { formatSize, useCounts } from '../numbers';
import MaintenanceFindings from './MaintenanceFindings.vue';

type Schedule = Schemas['MaintenanceScheduleOut'];
type Frequency = 'off' | 'daily' | 'weekly';
type Action = 'delete' | 'report';
type Message = 'saved' | 'started' | 'running' | 'invalid' | 'failed';

interface Form {
  frequency: Frequency;
  weekday: number;
  time: string;
  action: Action;
  graceHours: number;
  safetyOn: boolean;
  safetyShare: number;
}

const FREQUENCIES: Frequency[] = ['off', 'daily', 'weekly'];
const ACTIONS: Action[] = ['delete', 'report'];

const { t, locale } = useI18n();
const { number } = useCounts();
const runs = useSubscription('library.maintenance', {}, [0, 1]);
const schedule = ref<Schedule | null>(null);
const form = ref<Form | null>(null);
const saving = ref(false);
const starting = ref(false);
const confirming = ref(false);
const confirmingRun = ref(false);
const message = ref<Message | null>(null);

// Monday … Sunday in the reader's locale (2024-01-01 was a Monday).
const weekdays = computed(() =>
  Array.from({ length: 7 }, (_, index) =>
    new Intl.DateTimeFormat(locale.value, { weekday: 'long', timeZone: 'UTC' }).format(
      new Date(Date.UTC(2024, 0, 1 + index)),
    ),
  ),
);
// The newest run (the stream lists the runs newest first).
const run = computed(() => {
  const row = runs.value.rows.get(0);
  return row ? (row as unknown as MaintenanceRunRow) : null;
});
const running = computed(() => run.value?.status === 'running');

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'full', timeStyle: 'short' }).format(
    new Date(value),
  );
}

function summary(files: number, bytes: number): string {
  return t(
    'maintenance.summary',
    { n: number(files), size: formatSize(bytes, locale.value) },
    files,
  );
}

function toForm(value: Schedule): Form {
  return {
    frequency: value.enabled ? value.frequency : 'off',
    weekday: value.weekday ?? 6,
    time: value.time,
    action: value.options.action ?? 'delete',
    graceHours: value.options.grace_hours ?? 24,
    safetyOn: value.options.safety_share_percent !== null,
    safetyShare: value.options.safety_share_percent ?? 1,
  };
}

function valid(value: Form): boolean {
  const grace =
    Number.isInteger(value.graceHours) && value.graceHours >= 1 && value.graceHours <= 168;
  const share = !value.safetyOn || (value.safetyShare >= 0.1 && value.safetyShare <= 100);
  return grace && share && /^\d{2}:\d{2}$/.test(value.time);
}

async function load(): Promise<void> {
  const { data } = await getServices().api.GET('/api/v1/maintenance/schedule');
  if (!data) return;
  schedule.value = data;
  form.value = toForm(data);
}

async function save(): Promise<void> {
  if (!form.value) return;
  message.value = null;
  if (!valid(form.value)) {
    message.value = 'invalid';
    return;
  }
  const value = form.value;
  saving.value = true;
  try {
    const { data, response } = await getServices().api.PUT('/api/v1/maintenance/schedule', {
      body: {
        enabled: value.frequency !== 'off',
        frequency: value.frequency === 'weekly' ? 'weekly' : 'daily',
        time: value.time,
        weekday: value.frequency === 'weekly' ? value.weekday : null,
        options: {
          action: value.action,
          grace_hours: value.graceHours,
          safety_share_percent: value.safetyOn ? value.safetyShare : null,
        },
      },
    });
    if (data) {
      schedule.value = data;
      form.value = toForm(data);
      message.value = 'saved';
    } else {
      message.value = response.status === 422 ? 'invalid' : 'failed';
    }
  } finally {
    saving.value = false;
  }
}

async function runNow(): Promise<void> {
  starting.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST('/api/v1/maintenance/runs');
    if (response.status === 409) message.value = 'running';
    else message.value = data ? 'started' : 'failed';
  } finally {
    starting.value = false;
  }
}

async function confirmRun(): Promise<void> {
  confirming.value = false;
  if (!run.value) return;
  confirmingRun.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST(
      '/api/v1/maintenance/runs/{run_id}/confirm',
      { params: { path: { run_id: run.value.id } } },
    );
    if (response.status === 409) message.value = 'running';
    else message.value = data ? 'started' : 'failed';
  } finally {
    confirmingRun.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.maintenance__hint {
  margin: 0 0 var(--space-3);
  max-width: 70ch;
}

.maintenance__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.maintenance__group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2) var(--space-4);
  margin: 0;
  padding: 0;
  border: 0;
}

.maintenance__legend {
  width: 100%;
  margin-bottom: var(--space-1);
  font-weight: 600;
}

.maintenance__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  width: 100%;
}

.maintenance__choice {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
}

.maintenance__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.maintenance__field input,
.maintenance__field select {
  min-height: 44px;
  max-width: 220px;
  padding: 0 var(--space-2);
  color: inherit;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.maintenance__note {
  width: 100%;
  font-size: 0.875rem;
}

.maintenance__next,
.maintenance__message,
.maintenance__status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}

.maintenance__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-2);
}

.maintenance__subtitle {
  margin: var(--space-4) 0 var(--space-2);
  font-size: 1rem;
}

.maintenance__held {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin: var(--space-3) 0;
}

.maintenance__held p {
  margin: 0;
  max-width: 70ch;
}

.maintenance__dialog {
  width: min(520px, 100vw);
}
</style>
