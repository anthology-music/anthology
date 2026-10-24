<template>
  <div class="edit-switch" role="group" :aria-label="t('tagging.mode')">
    <button
      type="button"
      :aria-pressed="!modelValue"
      class="edit-switch__option"
      data-testid="mode-listen"
      @click="emit('update:modelValue', false)"
    >
      {{ t('tagging.listen') }}
    </button>
    <button
      type="button"
      :aria-pressed="modelValue"
      class="edit-switch__option"
      data-testid="mode-edit"
      @click="emit('update:modelValue', true)"
    >
      {{ t('tagging.edit') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

/** Hören / Editieren (mockup Lokal-Editieren). */
defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [editing: boolean] }>();
const { t } = useI18n();
</script>

<style scoped>
.edit-switch {
  display: inline-flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  overflow: hidden;
}

.edit-switch__option {
  min-height: var(--touch-target);
  padding: 0 var(--space-4);
  color: var(--color-text-secondary);
  background: none;
  border: 0;
  cursor: pointer;
}

.edit-switch__option[aria-pressed='true'] {
  color: var(--color-text);
  background: var(--color-active-bg);
  font-weight: var(--weight-medium);
}

.edit-switch__option:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}
</style>
