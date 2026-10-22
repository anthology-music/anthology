<template>
  <div class="import-row" :data-testid="`import-${row.id}`">
    <button
      type="button"
      class="import-row__title"
      :aria-expanded="expanded"
      @click="emit('toggle')"
    >
      <q-icon :name="expanded ? 'expand_less' : 'expand_more'" size="20px" aria-hidden="true" />
      <span class="item-list__main">
        <span class="import-row__name">{{ folderName(row.source_path) }}</span>
        <span class="text-muted item-list__sub mono">{{ row.source_path }}</span>
      </span>
    </button>
    <span class="import-row__mode text-muted">{{ t(`libraryImport.modes.${row.mode}`) }}</span>
    <span class="import-row__status" :data-status="row.status" data-testid="import-status">
      <q-icon :name="statusIcons[row.status]" size="18px" aria-hidden="true" />
      {{ t(`libraryImport.status.${row.status}`) }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import { folderName, statusIcons, type ImportRow } from '../imports';

defineProps<{ row: ImportRow; expanded: boolean }>();
const emit = defineEmits<{ toggle: [] }>();
const { t } = useI18n();
</script>

<style scoped>
.import-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: 100%;
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-divider);
}

.import-row__title {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  min-height: 44px;
  padding: 0;
  background: none;
  border: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.import-row__name,
.import-row__title .item-list__sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.import-row__status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  white-space: nowrap;
}

.import-row__status[data-status='done'] {
  color: var(--color-status-ok);
}

.import-row__status[data-status='failed'] {
  color: var(--color-status-error);
}

.import-row__status[data-status='scanning'],
.import-row__status[data-status='importing'] {
  color: var(--color-status-running);
}

@media (max-width: 599px) {
  .import-row__mode {
    display: none;
  }
}
</style>
