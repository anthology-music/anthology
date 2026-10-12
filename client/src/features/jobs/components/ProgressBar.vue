<template>
  <div class="progress">
    <div
      class="progress__track"
      role="progressbar"
      :aria-valuenow="value"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="label"
    >
      <div class="progress__bar" :style="{ width: `${value}%` }" />
    </div>
    <span class="progress__value mono">{{ value }}%</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{ value: number; label: string }>();
</script>

<style scoped>
.progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.progress__track {
  flex: 1;
  height: 6px;
  overflow: hidden;
  border-radius: var(--radius-pill);
  background: var(--color-border);
}

.progress__bar {
  height: 100%;
  background: var(--color-accent);
  transition: width 0.3s ease;
}

.progress__value {
  width: 4ch;
  text-align: right;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
