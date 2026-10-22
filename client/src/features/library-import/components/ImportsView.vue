<template>
  <section class="imports" aria-labelledby="imports-title">
    <div class="imports__header">
      <h2 id="imports-title" class="settings-section__title">{{ t('libraryImport.title') }}</h2>
      <q-btn
        unelevated
        no-caps
        color="primary"
        icon="create_new_folder"
        :label="t('libraryImport.importFolder')"
        data-testid="import-folder"
        @click="dialog = true"
      />
    </div>

    <p v-if="error" class="form-error" role="alert" data-testid="imports-error">
      <q-icon name="info" aria-hidden="true" />{{ t(`libraryImport.errors.${error}`) }}
    </p>
    <p v-if="subscription.total === 0" class="text-muted" data-testid="imports-empty">
      {{ t('libraryImport.empty') }}
    </p>
    <div v-else class="imports__list">
      <VirtualList :subscription="subscription" :label="t('libraryImport.title')">
        <template #default="{ row }">
          <ImportRow
            :row="importRow(row)"
            :expanded="selectedId === row.id"
            @toggle="toggle(row.id)"
          />
        </template>
      </VirtualList>
    </div>

    <ImportReport
      v-if="selected"
      :key="selected.id"
      :row="selected"
      @confirm="control(selected, 'confirm')"
      @cancel="control(selected, 'cancel')"
    />

    <ImportFolderDialog v-model="dialog" @started="(id) => (selectedId = id)" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import VirtualList from '@/components/VirtualList.vue';
import { getServices } from '@/services';
import type { Row } from '@/sync/subscription';
import { useSubscription } from '@/sync/useSubscription';

import type { ImportRow as ImportRowData } from '../imports';
import ImportFolderDialog from './ImportFolderDialog.vue';
import ImportReport from './ImportReport.vue';
import ImportRow from './ImportRow.vue';

type ErrorCode = 'invalid_state' | 'failed';

const { t } = useI18n();
const subscription = useSubscription('library_import.imports', {}, [0, 50]);
const dialog = ref(false);
const selectedId = ref<string | null>(null);
const error = ref<ErrorCode | null>(null);
const importRow = (row: Row) => row as unknown as ImportRowData;

const selected = computed(() => {
  if (!selectedId.value) return null;
  for (const row of subscription.value.rows.values()) {
    if (row.id === selectedId.value) return importRow(row);
  }
  return null;
});

function toggle(id: string): void {
  selectedId.value = selectedId.value === id ? null : id;
}

async function control(row: ImportRowData, action: 'confirm' | 'cancel'): Promise<void> {
  error.value = null;
  const { api } = getServices();
  const options = { params: { path: { import_id: row.id } } };
  const { error: failed } =
    action === 'confirm'
      ? await api.POST('/api/v1/library-imports/{import_id}/confirm', options)
      : await api.POST('/api/v1/library-imports/{import_id}/cancel', options);
  if (failed) {
    const detail = (failed as { detail?: unknown }).detail;
    error.value = detail === 'invalid_state' ? 'invalid_state' : 'failed';
  }
}
</script>

<style scoped>
.imports {
  margin-bottom: var(--space-8);
}

.imports__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

/* The list needs a bounded height (it scrolls inside). */
.imports__list {
  height: min(30vh, 320px);
  min-height: 160px;
}
</style>
