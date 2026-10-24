<template>
  <div class="selectable-row" :class="{ 'selectable-row--selected': selected }">
    <label class="selectable-row__check">
      <input
        type="checkbox"
        :checked="selected"
        :aria-label="label"
        :data-testid="`select-${id}`"
        @click="emit('toggle', ($event as MouseEvent).shiftKey)"
      />
    </label>
    <slot />
  </div>
</template>

<script setup lang="ts">
/** A list row with a checkbox in edit mode; shift-click selects a range. */
defineProps<{ id: string; selected: boolean; label: string }>();
const emit = defineEmits<{ toggle: [shift: boolean] }>();
</script>

<style scoped>
.selectable-row {
  display: flex;
  align-items: center;
  height: 100%;
}

.selectable-row--selected {
  background: var(--color-selection-bg);
}

.selectable-row__check {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: var(--touch-target);
  height: 100%;
}
</style>
