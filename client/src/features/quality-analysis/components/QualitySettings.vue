<template>
  <section class="settings-section" aria-labelledby="quality-title">
    <h2 id="quality-title" class="settings-section__title">{{ t('quality.title') }}</h2>
    <p class="text-muted quality__hint">{{ t('quality.hint') }}</p>

    <ul class="item-list">
      <li
        v-for="entry in counts"
        :key="entry.key"
        class="item-list__row"
        :data-testid="`quality-${entry.key}`"
      >
        <span class="item-list__main">{{ t(`quality.statuses.${entry.key}`) }}</span>
        <span class="mono quality__count">{{ number(entry.value) }}</span>
      </li>
    </ul>

    <div class="quality__actions">
      <q-checkbox v-model="full" :label="t('quality.full')" data-testid="quality-full" />
      <q-btn
        unelevated
        no-caps
        color="primary"
        icon="graphic_eq"
        :label="t('quality.start')"
        :loading="starting"
        data-testid="quality-start"
        @click="start"
      />
    </div>
    <p v-if="message" class="quality__message" role="status" data-testid="quality-message">
      <q-icon :name="message === 'started' ? 'check_circle' : 'info'" aria-hidden="true" />
      {{ t(`quality.messages.${message}`) }}
    </p>
  </section>
</template>

<script setup lang="ts">
import type { QualitySummaryRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useCounts } from '@/features/library/numbers';
import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

type Message = 'started' | 'running' | 'nothing' | 'failed';
const STATUSES = ['genuine', 'upscaled', 'suspicious', 'confirmed_genuine', 'unanalysed'] as const;

const { t } = useI18n();
const { number } = useCounts();
const subscription = useSubscription('quality_analysis.summary', {}, [0, 1]);
const full = ref(false);
const starting = ref(false);
const message = ref<Message | null>(null);

const counts = computed(() => {
  const row = subscription.value.rows.get(0) as unknown as QualitySummaryRow | undefined;
  return STATUSES.map((key) => ({ key, value: row ? row[key] : null }));
});

async function start(): Promise<void> {
  starting.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST('/api/v1/quality-analysis', {
      body: { full: full.value },
    });
    if (response.status === 409) message.value = 'running';
    else if (!data) message.value = 'failed';
    else message.value = data.job_id ? 'started' : 'nothing';
  } finally {
    starting.value = false;
  }
}
</script>

<style scoped>
.quality__hint {
  margin: 0 0 var(--space-3);
  max-width: 70ch;
}

.quality__count {
  min-width: 10ch;
  text-align: right;
}

.quality__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.quality__message {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-3) 0 0;
}
</style>
