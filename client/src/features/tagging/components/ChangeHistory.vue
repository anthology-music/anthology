<template>
  <section class="settings-section" aria-labelledby="change-history-title">
    <h2 id="change-history-title" class="settings-section__title">{{ t('tagging.history') }}</h2>
    <p class="text-muted change-history__hint">{{ t('tagging.historyHint') }}</p>
    <p class="text-muted" data-testid="tag-writes">
      {{ t('tagging.pendingWrites', { n: number(pending) }, pending) }}
      <template v-if="failed">
        · {{ t('tagging.failedWrites', { n: number(failed) }, failed) }}</template
      >
    </p>
    <p v-if="subscription.total === 0" class="text-muted" data-testid="history-empty">
      {{ t('tagging.historyEmpty') }}
    </p>
    <div v-else class="change-history">
      <VirtualList :subscription="subscription" :label="t('tagging.history')">
        <template #default="{ row }">
          <div class="change-history__row" :data-testid="`change-${row.id}`">
            <span class="item-list__main">
              <span class="change-history__summary">
                <template v-if="change(row).kind === 'undo'"
                  >{{ t('tagging.undoneEdit') }}:
                </template>
                {{ summary(change(row)) }}
              </span>
              <span class="text-muted item-list__sub">
                {{ change(row).user_name ?? t('tagging.system') }} ·
                {{ date(change(row).created_at) }} ·
                {{
                  t('tagging.changedOf', {
                    changed: number(change(row).changed),
                    items: number(change(row).items),
                  })
                }}
              </span>
            </span>
            <span v-if="!change(row).undoable" class="text-muted" data-testid="change-undone">
              {{ t('tagging.undone') }}
            </span>
            <q-btn
              v-else
              flat
              no-caps
              :disable="busy"
              :label="t('tagging.undo')"
              :data-testid="`undo-${row.id}`"
              @click="undo(row.id)"
            />
          </div>
        </template>
      </VirtualList>
    </div>
    <p v-if="message" role="status" data-testid="history-message">{{ message }}</p>
  </section>
</template>

<script setup lang="ts">
import type { ChangeSetRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { useCounts } from '@/features/library/numbers';
import { getServices } from '@/services';
import type { Row } from '@/sync/subscription';
import { useSubscription } from '@/sync/useSubscription';

/** The change history with undo (spec: tagging, Undo); editors and admins. */
const i18n = useI18n();
const { t, locale } = i18n;
const { number } = useCounts();
const subscription = useSubscription('tagging.changes', {}, [0, 50]);
const busy = ref(false);
const message = ref<string | null>(null);

const pending = computed(() => subscription.value.counters.pending_writes ?? 0);
const failed = computed(() => subscription.value.counters.failed_writes ?? 0);
const change = (row: Row) => row as unknown as ChangeSetRow;

function shown(value: unknown): string {
  if (value === null || value === undefined || value === '') return '–';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '–';
  if (typeof value === 'string') return value;
  return typeof value === 'number' || typeof value === 'boolean'
    ? value.toString()
    : JSON.stringify(value);
}

function summary(item: ChangeSetRow): string {
  const levels = (item.summary.fields ?? {}) as Record<string, Record<string, unknown>>;
  return Object.values(levels)
    .flatMap((fields) =>
      Object.entries(fields).map(([name, value]) => {
        const label = i18n.te(`tagging.fields.${name}`) ? t(`tagging.fields.${name}`) : name;
        return `${label}: ${shown(value)}`;
      }),
    )
    .join(' · ');
}

const date = (value: string) =>
  new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  );

async function undo(id: string): Promise<void> {
  busy.value = true;
  message.value = null;
  try {
    const { data, response } = await getServices().api.POST(
      '/api/v1/tagging/changes/{change_set_id}/undo',
      { params: { path: { change_set_id: id } } },
    );
    if (data) message.value = t('tagging.undoStarted');
    else if (response.status === 409) message.value = t('tagging.errors.already_undone');
    else message.value = t('tagging.errors.failed');
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.change-history__hint {
  margin: 0 0 var(--space-2);
  max-width: 70ch;
}

/* The list needs a bounded height (it scrolls inside). */
.change-history {
  height: min(40vh, 360px);
  min-height: 160px;
}

.change-history__row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 100%;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-divider);
}

.change-history__summary {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
