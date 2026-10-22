<template>
  <section class="settings-section" aria-labelledby="adoption-title">
    <h2 id="adoption-title" class="settings-section__title">{{ t('adoption.title') }}</h2>
    <p class="text-muted adoption__hint">{{ t('adoption.hint') }}</p>

    <p class="adoption__summary mono" data-testid="adoption-summary">
      <q-icon name="link" aria-hidden="true" />
      {{ summary }}
    </p>

    <fieldset class="adoption__modes">
      <legend class="adoption__legend">{{ t('adoption.mode') }}</legend>
      <label
        v-for="option in MODES"
        :key="option"
        class="adoption__mode"
        :data-testid="`adoption-mode-${option}`"
      >
        <input v-model="mode" type="radio" name="adoption-mode" :value="option" />
        {{ t(`adoption.modes.${option}`) }}
      </label>
    </fieldset>

    <div class="adoption__actions">
      <q-btn
        unelevated
        no-caps
        color="primary"
        icon="inventory_2"
        :label="t('adoption.start')"
        :disable="!files"
        :loading="starting"
        data-testid="adoption-start"
        @click="confirming = true"
      />
    </div>
    <p v-if="message" class="adoption__message" role="status" data-testid="adoption-message">
      <q-icon :name="message === 'started' ? 'check_circle' : 'info'" aria-hidden="true" />
      {{ t(`adoption.messages.${message}`) }}
    </p>

    <q-dialog v-model="confirming">
      <q-card class="adoption__dialog" data-testid="adoption-dialog">
        <q-card-section>
          <h3 class="settings-section__title">{{ t('adoption.confirmTitle') }}</h3>
          <p>
            {{ t('adoption.confirmText', { files: summary, mode: t(`adoption.modes.${mode}`) }) }}
          </p>
          <p class="text-muted">{{ t('adoption.hint') }}</p>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('adoption.cancel')" @click="confirming = false" />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="t('adoption.confirm')"
            data-testid="adoption-confirm"
            @click="start"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </section>
</template>

<script setup lang="ts">
import type { LibraryStorageRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

import { formatSize, useCounts } from '../numbers';

type Mode = 'move' | 'copy' | 'reflink';
type Message = 'started' | 'running' | 'nothing' | 'failed';
// Never hardlink: the bytes would stay shared with the referenced file.
const MODES: Mode[] = ['copy', 'move', 'reflink'];

const { t, locale } = useI18n();
const { number } = useCounts();
const subscription = useSubscription('library.storage', {}, [0, 1]);
const mode = ref<Mode>('copy');
const confirming = ref(false);
const starting = ref(false);
const message = ref<Message | null>(null);

const row = computed(
  () => subscription.value.rows.get(0) as unknown as LibraryStorageRow | undefined,
);
const files = computed(() => row.value?.referenced_files ?? 0);
const summary = computed(() =>
  row.value
    ? t(
        'adoption.summary',
        { n: number(files.value), size: formatSize(row.value.referenced_bytes, locale.value) },
        files.value,
      )
    : '…',
);

async function start(): Promise<void> {
  confirming.value = false;
  starting.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST('/api/v1/library/adoption', {
      body: { mode: mode.value },
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
.adoption__hint {
  margin: 0 0 var(--space-3);
  max-width: 70ch;
}

.adoption__summary,
.adoption__message {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
}

.adoption__modes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  border: none;
}

.adoption__legend {
  margin-bottom: var(--space-2);
  font-weight: var(--weight-medium);
}

.adoption__mode {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  cursor: pointer;
}

.adoption__actions {
  display: flex;
  justify-content: flex-end;
  margin: var(--space-3) 0;
}

.adoption__dialog {
  width: min(520px, 100vw);
}
</style>
