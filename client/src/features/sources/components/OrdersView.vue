<template>
  <section class="orders" :aria-label="t('sources.orders.title')" data-testid="orders">
    <div class="orders__summary" role="group" :aria-label="t('sources.orders.summary')">
      <div v-for="name in COUNTS" :key="name" class="orders__count">
        <span class="text-muted">{{ t(`sources.orders.counts.${name}`) }}</span>
        <span class="mono" :data-testid="`orders-${name}`">{{ number(totals[name]) }}</span>
      </div>
    </div>
    <h2 class="orders__title">{{ t('sources.orders.title') }}</h2>
    <p v-if="subscription.total === 0" class="text-muted">{{ t('sources.orders.none') }}</p>
    <ul class="orders__list">
      <li v-for="order in orders" :key="order.id" class="orders__order">
        <button
          type="button"
          class="orders__head"
          :aria-expanded="open === order.id"
          :data-testid="`order-${order.id}`"
          @click="open = open === order.id ? null : order.id"
        >
          <span class="mono orders__short">{{ order.short }}</span>
          <span class="orders__name">{{ order.title }}</span>
          <span class="text-muted">{{ t(`sources.orders.status.${order.status}`) }}</span>
          <span class="mono text-muted">{{ order.done }}/{{ order.total }}</span>
        </button>
        <OrderItems v-if="open === order.id" :order-id="order.id" />
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { OrderRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useCounts } from '@/features/library/numbers';
import { useSubscription } from '@/sync/useSubscription';

import OrderItems from './OrderItems.vue';

/** Download orders with their counts (spec: sources, Download orders; mockup Main). */
const COUNTS = ['total', 'done', 'running', 'waiting', 'failed'] as const;

const { t } = useI18n();
const { number } = useCounts();
const subscription = useSubscription('sources.orders', {}, [0, 50]);
const open = ref<string | null>(null);
const orders = computed(() =>
  [...subscription.value.rows.values()].map((row) => row as unknown as OrderRow),
);
const totals = computed(
  () =>
    Object.fromEntries(
      COUNTS.map((name) => [name, orders.value.reduce((sum, order) => sum + order[name], 0)]),
    ) as Record<(typeof COUNTS)[number], number>,
);
</script>

<style scoped>
.orders {
  margin-top: var(--space-5);
}

.orders__summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
}

.orders__count {
  display: flex;
  flex-direction: column;
}

.orders__title {
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--text-lg);
  font-weight: var(--weight-medium);
}

.orders__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.orders__head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  min-height: var(--touch-target);
  border: 0;
  border-bottom: 1px solid var(--color-divider);
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.orders__name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
