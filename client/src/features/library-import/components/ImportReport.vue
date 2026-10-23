<template>
  <section
    class="import-report"
    :aria-label="t('libraryImport.report.title', { path: row.source_path })"
  >
    <h3 class="import-report__title">
      {{ t('libraryImport.report.title', { path: row.source_path }) }}
    </h3>

    <p v-if="row.status === 'scanning' || row.status === 'importing'" class="text-muted">
      {{ t(`libraryImport.report.${row.status}`) }}
    </p>

    <template v-if="data">
      <ul class="item-list" data-testid="import-report">
        <li
          v-for="category in CATEGORIES"
          :key="category"
          class="item-list__row"
          :data-testid="`import-category-${category}`"
        >
          <span class="item-list__main">{{
            t(`libraryImport.report.categories.${category}`)
          }}</span>
          <span class="mono import-report__files">
            {{ files(data.categories[category].files) }}
          </span>
          <span class="mono import-report__size">
            {{ formatSize(data.categories[category].bytes, locale) }}
          </span>
        </li>
      </ul>
      <p class="import-report__line" data-testid="import-adds">
        <q-icon name="storage" aria-hidden="true" />
        {{ t('libraryImport.report.adds', { size: formatSize(data.adds_bytes, locale) }) }}
      </p>
      <p class="import-report__line" data-testid="import-managed">
        <q-icon :name="row.managed ? 'inventory_2' : 'link'" aria-hidden="true" />
        {{ t(row.managed ? 'libraryImport.report.managed' : 'libraryImport.report.referenced') }}
      </p>
      <p
        v-if="data.categories.replaces_lower_quality.files"
        class="import-report__line"
        data-testid="import-replaced"
      >
        <q-icon name="swap_horiz" aria-hidden="true" />
        {{
          t(
            row.delete_replaced
              ? 'libraryImport.report.replacedDeleted'
              : 'libraryImport.report.replacedKept',
            {
              n: number(data.categories.replaces_lower_quality.files),
            },
          )
        }}
      </p>
      <p v-if="row.status === 'done'" class="import-report__line" data-testid="import-result">
        <q-icon name="check_circle" aria-hidden="true" />
        {{ t('libraryImport.report.imported', { n: number(data.imported) }) }}
        <template v-if="data.failed.files">
          · {{ t('libraryImport.report.failed', { n: number(data.failed.files) }) }}
        </template>
      </p>
      <p v-if="row.status === 'reported'" class="text-muted">
        {{ t('libraryImport.report.confirmHint') }}
      </p>
    </template>

    <div class="import-report__actions">
      <template v-if="row.status === 'reported'">
        <q-btn
          flat
          no-caps
          :label="t('libraryImport.report.discard')"
          data-testid="import-cancel"
          @click="emit('cancel')"
        />
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="download_done"
          :label="t('libraryImport.report.confirm')"
          data-testid="import-confirm"
          @click="emit('confirm')"
        />
      </template>
      <q-btn
        v-else-if="row.status === 'scanning' || row.status === 'importing'"
        flat
        no-caps
        icon="close"
        :label="t('libraryImport.report.stop')"
        data-testid="import-cancel"
        @click="emit('cancel')"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatSize, useCounts } from '@/features/library/numbers';

import { CATEGORIES, report, type ImportRow } from '../imports';

const props = defineProps<{ row: ImportRow }>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();
const { t, locale } = useI18n();
const { number } = useCounts();
const data = computed(() => report(props.row));
const files = (count: number) => t('libraryImport.report.files', { n: number(count) }, count);
</script>

<style scoped>
.import-report {
  margin-top: var(--space-4);
}

.import-report__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-md);
  font-weight: var(--weight-medium);
  overflow-wrap: anywhere;
}

.import-report__files,
.import-report__size {
  min-width: 10ch;
  text-align: right;
}

.import-report__line {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-3) 0 0;
}

.import-report__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-3);
}
</style>
