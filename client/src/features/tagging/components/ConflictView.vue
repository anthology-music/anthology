<template>
  <div class="conflicts">
    <p class="conflicts__total" data-testid="conflicts-total">
      {{ t('conflicts.count', { n: number(subscription.total) }, subscription.total ?? 0) }}
    </p>
    <div v-if="selected.size" class="conflicts__bar" data-testid="conflicts-bar">
      <span>{{ t('tagging.selected', { n: number(selected.size) }, selected.size) }}</span>
      <q-btn
        unelevated
        no-caps
        color="primary"
        :disable="busy"
        :label="t('conflicts.accept')"
        data-testid="conflicts-accept-selected"
        @click="decideIds([...selected], 'accept')"
      />
      <q-btn
        outline
        no-caps
        :disable="busy"
        :label="t('conflicts.reject')"
        data-testid="conflicts-reject-selected"
        @click="decideIds([...selected], 'reject')"
      />
      <q-btn flat no-caps :label="t('tagging.clearSelection')" @click="selected.clear()" />
    </div>
    <div v-if="group && subscription.total" class="conflicts__group-actions">
      <q-btn
        flat
        no-caps
        :disable="busy"
        :label="t('conflicts.acceptGroup', { n: number(subscription.total) })"
        data-testid="conflicts-accept-group"
        @click="ask('accept')"
      />
      <q-btn
        flat
        no-caps
        :disable="busy"
        :label="t('conflicts.rejectGroup', { n: number(subscription.total) })"
        data-testid="conflicts-reject-group"
        @click="ask('reject')"
      />
    </div>
    <p v-if="message" role="status" data-testid="conflicts-message">{{ message }}</p>
    <p v-if="subscription.total === 0" class="text-muted" data-testid="conflicts-empty">
      {{ t('conflicts.empty') }}
    </p>
    <div v-else class="conflicts__list">
      <VirtualList :subscription="subscription" :label="t('conflicts.title')">
        <template #default="{ row }">
          <div
            class="conflict-row"
            :class="{ 'conflict-row--selected': selected.has(row.id) }"
            :data-testid="`conflict-${row.id}`"
          >
            <label class="conflict-row__check">
              <input
                type="checkbox"
                :checked="selected.has(row.id)"
                :aria-label="t('tagging.select', { name: entry(row).summary.subject })"
                @change="toggle(row.id)"
              />
            </label>
            <span class="item-list__main">
              <span class="conflict-row__subject">
                {{ entry(row).summary.subject }} · {{ fieldLabel(entry(row)) }}
              </span>
              <span class="text-muted item-list__sub">
                <span class="mono">{{ entry(row).summary.current ?? '–' }}</span>
                →
                <span class="mono">{{ entry(row).summary.proposed ?? '–' }}</span>
                · {{ t(`review.origins.${entry(row).origin}`) }}
              </span>
            </span>
            <q-btn
              flat
              dense
              no-caps
              :disable="busy"
              :label="t('conflicts.acceptOne')"
              :data-testid="`conflict-accept-${row.id}`"
              @click="decideIds([row.id], 'accept')"
            />
            <q-btn
              flat
              dense
              no-caps
              :disable="busy"
              :label="t('conflicts.keep')"
              :data-testid="`conflict-reject-${row.id}`"
              @click="decideIds([row.id], 'reject')"
            />
          </div>
        </template>
      </VirtualList>
    </div>

    <q-dialog v-model="confirming">
      <q-card data-testid="conflicts-dialog">
        <q-card-section>
          {{ t(`conflicts.confirm.${pending}`, { n: number(subscription.total) }) }}
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('tagging.cancel')" @click="confirming = false" />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="t('review.confirm')"
            data-testid="conflicts-confirm"
            @click="decideGroup"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import type { ReviewItemRow, TagConflictProposal } from '@anthology/api-types';
import { reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { useCounts } from '@/features/library/numbers';
import { type DecisionResult, decide, entry } from '@/features/review/review';
import { useSubscription } from '@/sync/useSubscription';

import type { ConflictGroup } from '../conflicts';

/** The open tag conflicts of one group (or all); a new group remounts it. */
const props = defineProps<{ group: ConflictGroup | null }>();

const { t } = useI18n();
const { number } = useCounts();
const params: Record<string, string> = { status: 'open' };
if (props.group) params[props.group.param] = props.group.value;
const subscription = useSubscription('tagging.conflicts', params, [0, 100]);
const selected = reactive(new Set<string>());
const busy = ref(false);
const message = ref<string | null>(null);
const confirming = ref(false);
const pending = ref<'accept' | 'reject'>('accept');

function fieldLabel(item: ReviewItemRow): string {
  const field = (item.proposal as unknown as TagConflictProposal).field;
  return t(`tagging.fields.${field}`);
}

function toggle(id: string): void {
  if (selected.has(id)) selected.delete(id);
  else selected.add(id);
}

function report(result: DecisionResult): void {
  if (result.kind === 'decided') message.value = t(`review.result.${result.status}`);
  else if (result.kind === 'job')
    message.value = t('review.result.job', { n: number(result.selected) }, result.selected);
  else if (result.kind === 'nothing') message.value = t('review.result.nothing');
  else message.value = t('review.errors.failed');
}

async function run(work: () => Promise<DecisionResult>): Promise<void> {
  busy.value = true;
  message.value = null;
  try {
    report(await work());
  } finally {
    busy.value = false;
  }
}

async function decideIds(ids: string[], decision: 'accept' | 'reject'): Promise<void> {
  await run(() => decide({ ids }, decision));
  for (const id of ids) selected.delete(id);
}

function ask(decision: 'accept' | 'reject'): void {
  pending.value = decision;
  confirming.value = true;
}

async function decideGroup(): Promise<void> {
  confirming.value = false;
  const rule = {
    status: 'open' as const,
    type: 'tag_conflict' as const,
    ...(props.group ? { [props.group.param]: props.group.value } : {}),
  };
  await run(() => decide({ rule }, pending.value));
}
</script>

<style scoped>
.conflicts {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}

.conflicts__total {
  margin: 0;
}

.conflicts__bar {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-selection-ring);
  border-radius: var(--radius-md);
}

.conflicts__group-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* The list needs a bounded height (it scrolls inside). */
.conflicts__list {
  height: calc(100vh - 320px);
  min-height: 300px;
}

.conflict-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 100%;
  padding-right: var(--space-3);
  border-bottom: 1px solid var(--color-divider);
}

.conflict-row--selected {
  background: var(--color-selection-bg);
}

.conflict-row__check {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: var(--touch-target);
  height: 100%;
}

.conflict-row__subject {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
