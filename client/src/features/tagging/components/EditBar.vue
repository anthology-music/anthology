<template>
  <div class="edit-bar" data-testid="edit-bar">
    <span data-testid="edit-count">
      {{ t('tagging.selected', { n: number(selection.count.value) }, selection.count.value) }}
    </span>
    <q-btn
      unelevated
      no-caps
      color="primary"
      :disable="!selection.count.value"
      :label="t('tagging.editTags')"
      data-testid="edit-tags"
      @click="editing = true"
    />
    <q-btn
      flat
      no-caps
      :label="t('tagging.selectAll')"
      data-testid="select-all"
      @click="selection.selectAll()"
    />
    <q-btn
      flat
      no-caps
      :disable="!selection.count.value"
      :label="t('tagging.clearSelection')"
      @click="selection.clear()"
    />
    <span v-if="message" role="status" class="edit-bar__message" data-testid="edit-message">
      {{ message }}
    </span>
    <TagEditor
      :open="editing"
      :selection="selection.selection.value"
      :count="selection.count.value"
      mode="tracks"
      @close="editing = false"
      @done="done"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useCounts } from '@/features/library/numbers';

import type { Selection } from '../selection';
import TagEditor, { type EditResult } from './TagEditor.vue';

/** The sticky action bar of edit mode with the number of selected tracks. */
const props = defineProps<{ selection: Selection }>();

const { t } = useI18n();
const { number } = useCounts();
const editing = ref(false);
const message = ref<string | null>(null);

function done(result: EditResult): void {
  message.value =
    result.kind === 'job'
      ? t('tagging.result.job', { n: number(result.items) }, result.items)
      : t('tagging.result.saved', { n: number(result.changed) }, result.changed);
  props.selection.clear();
}
</script>

<style scoped>
.edit-bar {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-raised);
  border: 1px solid var(--color-selection-ring);
  border-radius: var(--radius-md);
}

.edit-bar__message {
  margin-left: auto;
}
</style>
