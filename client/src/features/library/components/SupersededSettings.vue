<template>
  <section class="settings-section" aria-labelledby="superseded-title">
    <h2 id="superseded-title" class="settings-section__title">{{ t('superseded.title') }}</h2>
    <p class="text-muted superseded__hint">{{ t('superseded.hint') }}</p>

    <ul class="item-list">
      <li class="item-list__row" data-testid="superseded-managed">
        <span class="item-list__main">{{ t('superseded.managed') }}</span>
        <span class="mono">{{
          summary('superseded_managed_files', 'superseded_managed_bytes')
        }}</span>
      </li>
      <li class="item-list__row" data-testid="superseded-referenced">
        <span class="item-list__main">
          {{ t('superseded.referenced') }}
          <span class="text-muted item-list__sub">{{ t('superseded.neverDeleted') }}</span>
        </span>
        <span class="mono">{{ referenced }}</span>
      </li>
    </ul>

    <div v-if="subscription.total" class="superseded__list">
      <VirtualList :subscription="subscription" :label="t('superseded.title')">
        <template #default="{ row }">
          <div class="superseded-row" :data-testid="`superseded-${row.id}`">
            <span class="item-list__main">
              <span class="superseded-row__title"
                >{{ file(row).title }} · {{ file(row).artist }}</span
              >
              <span class="text-muted item-list__sub mono superseded-row__title">
                {{ file(row).path }}
              </span>
            </span>
            <span class="badge" :data-testid="`superseded-mode-${row.id}`">
              <q-icon
                :name="file(row).storage_mode === 'managed' ? 'inventory_2' : 'link'"
                size="14px"
                aria-hidden="true"
              />
              {{ t(`superseded.modes.${file(row).storage_mode}`) }}
            </span>
            <span class="mono text-muted">{{ formatSize(file(row).size_bytes, locale) }}</span>
          </div>
        </template>
      </VirtualList>
    </div>

    <div class="superseded__actions">
      <q-btn
        unelevated
        no-caps
        color="negative"
        icon="delete_sweep"
        :label="t('superseded.delete')"
        :disable="!managedFiles"
        :loading="starting"
        data-testid="superseded-delete"
        @click="confirming = true"
      />
    </div>
    <p v-if="message" class="superseded__message" role="status" data-testid="superseded-message">
      <q-icon :name="message === 'started' ? 'check_circle' : 'info'" aria-hidden="true" />
      {{ t(`superseded.messages.${message}`) }}
    </p>

    <q-dialog v-model="confirming">
      <q-card class="superseded__dialog" data-testid="superseded-dialog">
        <q-card-section>
          <h3 class="settings-section__title">{{ t('superseded.confirmTitle') }}</h3>
          <p>
            {{
              t('superseded.confirmText', {
                files: summary('superseded_managed_files', 'superseded_managed_bytes'),
              })
            }}
          </p>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('superseded.cancel')" @click="confirming = false" />
          <q-btn
            unelevated
            no-caps
            color="negative"
            :label="t('superseded.confirm')"
            data-testid="superseded-confirm"
            @click="start"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </section>
</template>

<script setup lang="ts">
import type { LibrarySupersededRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { getServices } from '@/services';
import type { Row } from '@/sync/subscription';
import { useSubscription } from '@/sync/useSubscription';

import { formatSize, useCounts } from '../numbers';

type Message = 'started' | 'running' | 'nothing' | 'failed';
type CounterName =
  'superseded_files' | 'superseded_bytes' | 'superseded_managed_files' | 'superseded_managed_bytes';

const { t, locale } = useI18n();
const { number } = useCounts();
const subscription = useSubscription('library.superseded', {}, [0, 50]);
const confirming = ref(false);
const starting = ref(false);
const message = ref<Message | null>(null);
const file = (row: Row) => row as unknown as LibrarySupersededRow;

const counter = (name: CounterName): number | null => {
  const counters = subscription.value.counters as Record<string, number> | null | undefined;
  return counters?.[name] ?? null;
};
const managedFiles = computed(() => counter('superseded_managed_files') ?? 0);

function format(files: number | null, bytes: number | null): string {
  if (files === null || bytes === null) return '…';
  return t(
    'superseded.summary',
    { n: number(files), size: formatSize(bytes, locale.value) },
    files,
  );
}

function summary(files: CounterName, bytes: CounterName): string {
  return format(counter(files), counter(bytes));
}

const referenced = computed(() => {
  const files = counter('superseded_files');
  const bytes = counter('superseded_bytes');
  const managed = counter('superseded_managed_files');
  const managedBytes = counter('superseded_managed_bytes');
  if (files === null || bytes === null || managed === null || managedBytes === null) return '…';
  return format(files - managed, bytes - managedBytes);
});

async function start(): Promise<void> {
  confirming.value = false;
  starting.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST('/api/v1/library/superseded/deletion');
    if (response.status === 409) message.value = 'running';
    else if (!data) message.value = 'failed';
    else message.value = data.job_id ? 'started' : 'nothing';
  } finally {
    starting.value = false;
  }
}
</script>

<style scoped>
.superseded__hint {
  margin: 0 0 var(--space-3);
  max-width: 70ch;
}

/* The list needs a bounded height (it scrolls inside). */
.superseded__list {
  height: min(30vh, 320px);
  min-height: 160px;
  margin-top: var(--space-3);
}

.superseded-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 100%;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-divider);
}

.superseded-row__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.superseded__actions {
  display: flex;
  justify-content: flex-end;
  margin: var(--space-3) 0;
}

.superseded__message {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}

.superseded__dialog {
  width: min(520px, 100vw);
}
</style>
