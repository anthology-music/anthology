<template>
  <div
    ref="viewport"
    class="vlist"
    role="list"
    :aria-label="label"
    :aria-busy="loading || undefined"
    tabindex="0"
    @scroll.passive="onScroll"
    @keydown="onKeydown"
  >
    <!-- Sticky layer: always fills the viewport; rows move inside it by `offset`. -->
    <div class="vlist__layer" :style="{ height: `${viewportHeight}px` }">
      <div class="vlist__rows" :style="{ transform: `translateY(${-visible.offset}px)` }">
        <div
          v-for="position in positions"
          :key="position"
          class="vlist__row"
          role="listitem"
          :aria-setsize="total"
          :aria-posinset="position + 1"
          :style="{ height: `${rowHeight}px` }"
        >
          <slot v-if="rowAt(position)" :row="rowAt(position)!" :position="position" />
          <div v-else class="vlist__skeleton" aria-hidden="true">
            <span class="vlist__skeleton-bar" />
            <span class="vlist__skeleton-bar vlist__skeleton-bar--short" />
          </div>
        </div>
      </div>
    </div>
    <div class="vlist__spacer" :style="{ height: `${spacerHeight}px` }" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import type { Row, Subscription } from '@/sync/subscription';

import { geometry, requestWindow, scrollTopFor, visibleRows } from './virtualGeometry';

const props = withDefaults(
  defineProps<{
    subscription: Subscription;
    label: string;
    /** Must match --row-height in docs/design/tokens.css. */
    rowHeight?: number;
    /** Rows requested beyond the visible ones on each side. */
    buffer?: number;
    /** Rows kept in memory around the window; others are dropped. */
    keep?: number;
    /** Used until the real height is measured (e.g. in tests without layout). */
    fallbackHeight?: number;
    debounceMs?: number;
    /** Safety cap for rendered rows (protects against an unbounded container height). */
    maxRendered?: number;
  }>(),
  {
    rowHeight: 52,
    buffer: 50,
    keep: 2000,
    fallbackHeight: 600,
    debounceMs: 60,
    maxRendered: 200,
  },
);

const viewport = ref<HTMLElement | null>(null);
const scrollTop = ref(0);
const viewportHeight = ref(props.fallbackHeight);
let timer: ReturnType<typeof setTimeout> | null = null;
let resizeObserver: ResizeObserver | null = null;

// The subscription object stays the same; its changes are counted to re-evaluate.
const revision = ref(0);
let stopListening: (() => void) | null = null;
watch(
  () => props.subscription,
  (subscription) => {
    stopListening?.();
    stopListening = subscription.onChange(() => revision.value++);
    revision.value++;
  },
  { immediate: true },
);

const total = computed(() => (revision.value, props.subscription.total ?? 0));
const loading = computed(() => (revision.value, props.subscription.total === null));
const geo = computed(() => geometry(total.value, props.rowHeight, viewportHeight.value));
const visible = computed(() =>
  visibleRows(scrollTop.value, total.value, props.rowHeight, viewportHeight.value, geo.value),
);
const positions = computed(() =>
  Array.from(
    { length: Math.min(visible.value.count, props.maxRendered) },
    (_, index) => visible.value.first + index,
  ),
);
// The sticky layer already occupies one viewport height of the scroll content.
const spacerHeight = computed(() => Math.max(0, geo.value.scrollHeight - viewportHeight.value));

function rowAt(position: number): Row | undefined {
  void revision.value;
  return props.subscription.rows.get(position);
}

function requestRows(): void {
  if (props.subscription.total === null) return;
  const [start, end] = requestWindow(visible.value, total.value, props.buffer);
  const [currentStart, currentEnd] = props.subscription.currentWindow;
  if (start === currentStart && end === currentEnd) return;
  props.subscription.setWindow(start, end);
  props.subscription.prune(start - props.keep, end + props.keep);
}

function scheduleRequest(): void {
  if (timer) clearTimeout(timer);
  timer = setTimeout(requestRows, props.debounceMs);
}

function onScroll(): void {
  scrollTop.value = viewport.value?.scrollTop ?? 0;
  scheduleRequest();
}

/** Scroll so that `position` is at the top (used by keyboard navigation and tests). */
function scrollToPosition(position: number): void {
  const top = scrollTopFor(position, props.rowHeight, geo.value);
  if (viewport.value) viewport.value.scrollTop = top;
  scrollTop.value = top;
  scheduleRequest();
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Home') scrollToPosition(0);
  else if (event.key === 'End') scrollToPosition(Math.max(0, total.value - 1));
  else return;
  event.preventDefault();
}

watch(total, scheduleRequest);

onMounted(() => {
  const element = viewport.value;
  if (!element) return;
  const measure = () => {
    if (element.clientHeight <= 0) return;
    viewportHeight.value = element.clientHeight;
    if (import.meta.env.DEV && element.clientHeight > 4 * globalThis.innerHeight) {
      console.warn('VirtualList: the container height is not bounded; give it a fixed height.');
    }
  };
  measure();
  resizeObserver = new ResizeObserver(() => {
    measure();
    scheduleRequest();
  });
  resizeObserver.observe(element);
});

onBeforeUnmount(() => {
  stopListening?.();
  if (timer) clearTimeout(timer);
  resizeObserver?.disconnect();
});

defineExpose({ scrollToPosition });
</script>

<style scoped>
.vlist {
  position: relative;
  height: 100%;
  overflow-y: auto;
  overflow-anchor: none;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.vlist:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.vlist__layer {
  position: sticky;
  top: 0;
  overflow: hidden;
}

.vlist__row {
  display: flex;
  align-items: center;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-divider);
}

.vlist__skeleton {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-2);
}

.vlist__skeleton-bar {
  display: block;
  width: 40%;
  height: 10px;
  border-radius: var(--radius-sm);
  background: var(--color-skeleton);
}

.vlist__skeleton-bar--short {
  width: 24%;
}
</style>
