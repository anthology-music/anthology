<template>
  <div class="review">
    <form class="review__filters" :aria-label="t('review.filters')" @submit.prevent>
      <label class="review__filter">
        {{ t('review.status') }}
        <select
          :value="filter.status"
          data-testid="review-filter-status"
          @change="change('status', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="status in STATUSES" :key="status" :value="status">
            {{ t(`review.statuses.${status}`) }} ({{ number(count(`status.${status}`)) }})
          </option>
        </select>
      </label>
      <label class="review__filter">
        {{ t('review.type') }}
        <select
          :value="filter.type ?? ''"
          data-testid="review-filter-type"
          @change="change('type', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('review.all') }}</option>
          <option v-for="type in TYPES" :key="type" :value="type">
            {{ t(`review.types.${type}`) }} ({{ number(count(`type.${type}`)) }})
          </option>
        </select>
      </label>
      <label class="review__filter">
        {{ t('review.origin') }}
        <select
          :value="filter.origin ?? ''"
          data-testid="review-filter-origin"
          @change="change('origin', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('review.all') }}</option>
          <option v-for="origin in ORIGINS" :key="origin" :value="origin">
            {{ t(`review.origins.${origin}`) }}
          </option>
        </select>
      </label>
      <label class="review__filter">
        {{ t('review.confidence') }}
        <select
          :value="filter.confidence ?? ''"
          data-testid="review-filter-confidence"
          @change="change('confidence', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('review.all') }}</option>
          <option v-for="confidence in CONFIDENCES" :key="confidence" :value="confidence">
            {{ t(`review.confidences.${confidence}`) }}
          </option>
        </select>
      </label>
    </form>

    <p class="review__total" data-testid="review-total">
      {{ t('review.count', { n: number(subscription.total) }, subscription.total ?? 0) }}
    </p>

    <div v-if="actionable && selected.size" class="review__bar" data-testid="review-bar">
      <span>{{ t('review.selected', { n: number(selected.size) }, selected.size) }}</span>
      <template v-if="bulkChoices.length">
        <q-btn
          v-for="choice in bulkChoices"
          :key="choice"
          unelevated
          no-caps
          color="primary"
          :disable="busy"
          :label="t(`review.choices.${choice}`)"
          @click="decideSelected('accept', choice)"
        />
      </template>
      <q-btn
        v-else-if="filter.type"
        unelevated
        no-caps
        color="primary"
        :disable="busy"
        :label="t(`review.accept.${filter.type}`)"
        data-testid="review-bar-accept"
        @click="decideSelected('accept', null)"
      />
      <q-btn
        outline
        no-caps
        :disable="busy"
        :label="t('review.rejectSelected')"
        data-testid="review-bar-reject"
        @click="decideSelected('reject', null)"
      />
      <q-btn
        flat
        no-caps
        :disable="busy"
        :label="filter.status === 'open' ? t('review.defer') : t('review.reopen')"
        data-testid="review-bar-defer"
        @click="decideSelected(filter.status === 'open' ? 'defer' : 'reopen', null)"
      />
      <q-btn flat no-caps :label="t('review.clearSelection')" @click="selected.clear()" />
    </div>

    <div v-if="actionable && subscription.total" class="review__rule">
      <q-btn
        flat
        no-caps
        :disable="busy"
        :label="t('review.rejectAll', { n: number(subscription.total) })"
        data-testid="review-reject-all"
        @click="askRule('reject')"
      />
      <q-btn
        v-if="filter.type && !bulkChoices.length"
        flat
        no-caps
        :disable="busy"
        :label="t('review.acceptAll', { n: number(subscription.total) })"
        data-testid="review-accept-all"
        @click="askRule('accept')"
      />
    </div>

    <p v-if="message" class="review__message" role="status" data-testid="review-message">
      {{ message }}
    </p>

    <div class="review__body">
      <p v-if="subscription.total === 0" class="text-muted" data-testid="review-empty">
        {{ t(`review.empty.${filter.status}`) }}
      </p>
      <div v-else class="review__list">
        <VirtualList :subscription="subscription" :label="t('review.title')">
          <template #default="{ row }">
            <div
              class="review-row"
              :class="{
                'review-row--selected': selected.has(row.id),
                'review-row--focused': focusedId === row.id,
              }"
              :data-testid="`review-row-${entry(row).subject_id}`"
            >
              <label v-if="actionable" class="review-row__check">
                <input
                  type="checkbox"
                  :checked="selected.has(row.id)"
                  :aria-label="t('review.select', { name: entry(row).summary.subject })"
                  @change="toggle(row.id)"
                />
              </label>
              <button type="button" class="review-row__open" @click="focusedId = row.id">
                <span class="review-row__confidence" :data-confidence="entry(row).confidence">
                  <q-icon :name="CONFIDENCE_ICONS[entry(row).confidence]" aria-hidden="true" />
                  {{ t(`review.confidences.${entry(row).confidence}`) }}
                </span>
                <span class="item-list__main">
                  <span class="review-row__subject">{{ entry(row).summary.subject }}</span>
                  <span class="text-muted item-list__sub">
                    {{ t(`review.types.${entry(row).type}`) }} ·
                    {{ t(`review.origins.${entry(row).origin}`) }}
                  </span>
                </span>
              </button>
            </div>
          </template>
        </VirtualList>
      </div>
      <ReviewDetail
        v-if="focused"
        :item="focused"
        :busy="busy"
        class="review__detail"
        @decide="decideFocused"
      />
    </div>

    <q-dialog v-model="ruleDialog">
      <q-card class="review__dialog" data-testid="review-rule-dialog">
        <q-card-section>
          <p>
            {{ t(`review.ruleConfirm.${pendingRule}`, { n: number(subscription.total) }) }}
          </p>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('review.cancel')" @click="ruleDialog = false" />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="t('review.confirm')"
            data-testid="review-rule-confirm"
            @click="decideRule"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import type { Confidence, ReviewItemRow } from '@anthology/api-types';
import { computed, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { useCounts } from '@/features/library/numbers';
import { useSubscription } from '@/sync/useSubscription';

import {
  CONFIDENCES,
  type Decision,
  type DecisionResult,
  decide,
  entry,
  filterParams,
  ORIGINS,
  type ReviewFilter,
  STATUSES,
  TYPES,
} from '../review';
import ReviewDetail from './ReviewDetail.vue';

/** The review list for one filter; a new filter remounts it with a new subscription. */
const props = defineProps<{ filter: ReviewFilter }>();
const emit = defineEmits<{ 'update:filter': [filter: ReviewFilter] }>();

const CONFIDENCE_ICONS: Record<Confidence, string> = {
  high: 'verified',
  medium: 'help_outline',
  low: 'report_problem',
};

const { t } = useI18n();
const { number } = useCounts();
const subscription = useSubscription('review.items', filterParams(props.filter), [0, 100]);
const selected = reactive(new Set<string>());
const focusedId = ref<string | null>(null);
const busy = ref(false);
const message = ref<string | null>(null);
const ruleDialog = ref(false);
const pendingRule = ref<'accept' | 'reject'>('reject');

const actionable = computed(
  () => props.filter.status === 'open' || props.filter.status === 'deferred',
);
const count = (name: string) => subscription.value.counters[name] ?? 0;

const focused = computed<ReviewItemRow | null>(() => {
  if (!focusedId.value) return null;
  for (const row of subscription.value.rows.values()) {
    if (row.id === focusedId.value) return entry(row);
  }
  return null;
});

// Types with two answers (quality findings) are accepted with one of them.
const bulkChoices = computed(() =>
  props.filter.type === 'quality_finding' ? ['genuine', 'upscaled'] : [],
);

function change(name: keyof ReviewFilter, value: string): void {
  const next = { ...props.filter, [name]: name === 'status' ? value : value || null };
  emit('update:filter', next);
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
  else message.value = t(`review.errors.${result.code}`, t('review.errors.failed'));
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

async function decideFocused(decision: Decision, choice: string | null): Promise<void> {
  const item = focused.value;
  if (!item) return;
  await run(() => decide({ ids: [item.id] }, decision, choice));
}

async function decideSelected(decision: Decision, choice: string | null): Promise<void> {
  const ids = [...selected];
  await run(() => decide({ ids }, decision, choice));
  selected.clear();
}

function askRule(decision: 'accept' | 'reject'): void {
  pendingRule.value = decision;
  ruleDialog.value = true;
}

async function decideRule(): Promise<void> {
  ruleDialog.value = false;
  await run(() => decide({ rule: props.filter }, pendingRule.value));
}
</script>

<style scoped>
.review {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.review__filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.review__filter {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.review__filter select {
  min-height: var(--touch-target);
  padding: 0 var(--space-2);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.review__total,
.review__message {
  margin: 0;
}

.review__bar {
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

.review__rule {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.review__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-4);
  align-items: start;
}

/* The list needs a bounded height (it scrolls inside). */
.review__list {
  height: calc(100vh - 320px);
  min-height: 300px;
}

.review-row {
  display: flex;
  align-items: center;
  height: 100%;
  border-bottom: 1px solid var(--color-divider);
}

.review-row--selected {
  background: var(--color-selection-bg);
}

.review-row--focused {
  box-shadow: inset 3px 0 0 var(--color-accent);
}

.review-row__check {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: var(--touch-target);
  height: 100%;
}

.review-row__open {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  height: 100%;
  padding: 0 var(--space-3);
  color: inherit;
  text-align: left;
  background: none;
  border: 0;
  cursor: pointer;
}

.review-row__open:hover {
  background: var(--color-hover);
}

.review-row__open:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

.review-row__confidence {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-width: 10ch;
  font-size: var(--text-sm);
}

.review-row__confidence[data-confidence='high'] {
  color: var(--color-status-ok);
}

.review-row__confidence[data-confidence='low'] {
  color: var(--color-status-warning);
}

.review-row__subject {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

@media (max-width: 899px) {
  .review__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .review__list {
    height: 50vh;
  }
}
</style>
