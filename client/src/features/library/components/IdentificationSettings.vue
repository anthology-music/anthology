<template>
  <section class="settings-section" aria-labelledby="identification-title">
    <h2 id="identification-title" class="settings-section__title">
      {{ t('identification.title') }}
    </h2>
    <p class="text-muted identification__hint">{{ t('identification.hint') }}</p>

    <ul class="item-list identification__counts">
      <li
        v-for="entry in counts"
        :key="entry.key"
        class="item-list__row"
        :data-testid="`identification-${entry.key}`"
      >
        <span class="item-list__main">{{ t(`identification.outcomes.${entry.key}`) }}</span>
        <span class="mono identification__count">{{ number(entry.value) }}</span>
      </li>
    </ul>

    <div class="identification__actions">
      <q-checkbox
        v-model="full"
        :label="t('identification.full')"
        data-testid="identification-full"
      />
      <q-btn
        unelevated
        no-caps
        color="primary"
        icon="travel_explore"
        :label="t('identification.start')"
        :loading="starting"
        data-testid="identification-start"
        @click="start"
      />
    </div>
    <p
      v-if="message"
      class="identification__message"
      role="status"
      data-testid="identification-message"
    >
      <q-icon :name="message === 'running' ? 'info' : 'check_circle'" aria-hidden="true" />
      {{ t(`identification.messages.${message}`) }}
    </p>

    <template v-if="lookup">
      <p class="identification__estimate" data-testid="identification-estimate">
        {{ t('identification.estimate', { duration: duration(lookup.estimated_seconds) }) }}
        <span class="text-muted">
          ·
          {{
            lookup.mirror_configured
              ? t(`identification.mirror.${lookup.mirror_status ?? 'unavailable'}`)
              : t('identification.mirror.none')
          }}
        </span>
      </p>
      <p
        v-if="lookup.mirror_recommended"
        class="identification__recommendation"
        role="note"
        data-testid="identification-recommendation"
      >
        <q-icon name="lightbulb" aria-hidden="true" />
        {{ t('identification.recommendation') }}
      </p>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { LibraryIdentificationRow, Schemas } from '@anthology/api-types';
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useAuthStore } from '@/features/users/store';
import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

import { useCounts } from '../numbers';

type Message = 'started' | 'running' | 'nothing' | 'failed';
const OUTCOMES = [
  'isrc',
  'fingerprint',
  'no_match',
  'duplicate',
  'not_possible',
  'unchecked',
] as const;

const { t, locale } = useI18n();
const { number } = useCounts();
const auth = useAuthStore();
const subscription = useSubscription('library.identification', {}, [0, 1]);
const full = ref(false);
const starting = ref(false);
const message = ref<Message | null>(null);
const lookup = ref<Schemas['LookupStatusOut'] | null>(null);

const counts = computed(() => {
  const row = subscription.value.rows.get(0) as unknown as LibraryIdentificationRow | undefined;
  return OUTCOMES.map((key) => ({ key, value: row ? row[key] : null }));
});

/** Seconds as minutes, hours or days in the reader's locale. */
function duration(seconds: number): string {
  const format = (value: number, unit: 'minute' | 'hour' | 'day') =>
    new Intl.NumberFormat(locale.value, {
      style: 'unit',
      unit,
      unitDisplay: 'long',
      maximumFractionDigits: 1,
    }).format(value);
  if (seconds < 3600) return format(Math.ceil(seconds / 60), 'minute');
  if (seconds < 86_400) return format(seconds / 3600, 'hour');
  return format(seconds / 86_400, 'day');
}

async function loadLookupStatus(): Promise<void> {
  if (!auth.isAdmin) return;
  const { data } = await getServices().api.GET('/api/v1/metadata-lookup/status');
  lookup.value = data ?? null;
}

async function start(): Promise<void> {
  starting.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST('/api/v1/library/identification', {
      body: { full: full.value },
    });
    if (response.status === 409) message.value = 'running';
    else if (!data) message.value = 'failed';
    else message.value = data.job_id ? 'started' : 'nothing';
    await loadLookupStatus();
  } finally {
    starting.value = false;
  }
}

onMounted(loadLookupStatus);
</script>

<style scoped>
.identification__hint {
  margin: 0 0 var(--space-3);
  max-width: 70ch;
}

.identification__count {
  min-width: 10ch;
  text-align: right;
}

.identification__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.identification__message,
.identification__recommendation {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-3) 0 0;
}

.identification__recommendation {
  color: var(--color-status-warning);
}

.identification__estimate {
  margin: var(--space-3) 0 0;
}
</style>
