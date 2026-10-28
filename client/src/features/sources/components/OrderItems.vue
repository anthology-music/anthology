<template>
  <ul class="order-items" :data-testid="`order-items-${orderId}`">
    <li
      v-for="item in items"
      :key="item.id"
      class="order-items__item"
      :data-testid="`order-item-${item.position}`"
    >
      <span class="order-items__title">{{ item.title }}</span>
      <span class="text-muted">{{ item.artist }}</span>
      <q-linear-progress
        v-if="item.state === 'running' || item.state === 'waiting'"
        :value="item.progress"
        class="order-items__progress"
        :aria-label="t('sources.orders.progress', { title: item.title })"
      />
      <span class="order-items__state">
        {{
          item.outcome
            ? t(`sources.orders.outcomes.${item.outcome}`)
            : t(`sources.orders.states.${item.state}`)
        }}
      </span>
    </li>
  </ul>
</template>

<script setup lang="ts">
import type { OrderItemRow } from '@anthology/api-types';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { useSubscription } from '@/sync/useSubscription';

/** The tracks of one order with progress and outcome. */
const props = defineProps<{ orderId: string }>();

const { t } = useI18n();
const subscription = useSubscription('sources.order.items', { order_id: props.orderId }, [0, 500]);
const items = computed(() =>
  [...subscription.value.rows.values()].map((row) => row as unknown as OrderItemRow),
);
</script>

<style scoped>
.order-items {
  margin: 0 0 var(--space-3);
  padding: 0 0 0 var(--space-5);
  list-style: none;
}

.order-items__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.6fr) 120px auto;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target);
}

.order-items__progress {
  grid-column: 3;
}

.order-items__state {
  grid-column: 4;
}
</style>
