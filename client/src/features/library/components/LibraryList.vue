<template>
  <p v-if="subscription.total === 0" class="text-muted library-list__empty">{{ empty }}</p>
  <div v-else class="library-list">
    <VirtualList
      ref="list"
      :subscription="subscription"
      :label="label"
      :initial-position="initialPosition"
    >
      <template #default="{ row, position }">
        <slot :row="row" :position="position" :row-at="rowAt" />
      </template>
    </VirtualList>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';

import VirtualList from '@/components/VirtualList.vue';
import { useSubscription } from '@/sync/useSubscription';

import { useLibraryPositions } from '../positions';

/** A library list on a subscription that keeps its scroll position for the session. */
const props = defineProps<{
  stream: string;
  params?: Record<string, unknown>;
  /** Key of the remembered scroll position (route name plus parameter). */
  positionKey: string;
  label: string;
  empty: string;
}>();

defineSlots<{
  default(props: {
    row: Record<string, unknown>;
    position: number;
    rowAt: (position: number) => Record<string, unknown> | undefined;
  }): unknown;
}>();

const positions = useLibraryPositions();
const initialPosition = positions.position(props.positionKey);
// Start with the window around the restored position, not at the top.
const start = Math.max(0, initialPosition - 50);
const subscription = useSubscription(props.stream, props.params ?? {}, [start, start + 100]);
const list = ref<InstanceType<typeof VirtualList> | null>(null);
// Loaded rows by position (e.g. for selecting a range with shift-click).
const rowAt = (position: number) => subscription.value.rows.get(position);
defineExpose({ total: () => subscription.value.total });

onBeforeUnmount(() => {
  if (list.value) positions.remember(props.positionKey, list.value.firstVisible());
});
</script>

<style scoped>
/* The list needs a bounded height (it scrolls inside). */
.library-list {
  height: calc(100vh - 260px);
  min-height: 300px;
}

.library-list__empty {
  margin: var(--space-4) 0;
}
</style>
