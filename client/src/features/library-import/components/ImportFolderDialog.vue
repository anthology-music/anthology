<template>
  <q-dialog v-model="open" @show="browse(null)">
    <q-card class="import-dialog" data-testid="import-dialog">
      <q-card-section>
        <h2 class="settings-section__title">{{ t('libraryImport.dialog.title') }}</h2>
        <p class="import-dialog__path mono" data-testid="import-path">
          {{ listing?.path ?? t('libraryImport.dialog.roots') }}
        </p>
      </q-card-section>

      <q-card-section class="import-dialog__folders">
        <ul class="item-list" :aria-label="t('libraryImport.dialog.roots')">
          <li v-if="listing?.path" class="item-list__row">
            <button
              type="button"
              class="import-dialog__folder"
              data-testid="import-up"
              @click="browse(listing.parent)"
            >
              <q-icon name="arrow_upward" aria-hidden="true" />
              {{ t('libraryImport.dialog.up') }}
            </button>
          </li>
          <li v-for="folder in listing?.folders ?? []" :key="folder.path" class="item-list__row">
            <button
              type="button"
              class="import-dialog__folder"
              :aria-label="t('libraryImport.dialog.open', { name: folder.name })"
              :data-testid="`import-folder-${folder.name}`"
              @click="browse(folder.path)"
            >
              <q-icon name="folder" aria-hidden="true" />
              {{ folder.name }}
            </button>
          </li>
          <li
            v-if="listing && listing.folders.length === 0"
            class="item-list__row text-muted"
            data-testid="import-no-folders"
          >
            {{
              t(listing.path ? 'libraryImport.dialog.noFolders' : 'libraryImport.dialog.noRoots')
            }}
          </li>
        </ul>
      </q-card-section>

      <q-card-section v-if="listing?.modes">
        <fieldset class="import-dialog__modes">
          <legend class="import-dialog__legend">{{ t('libraryImport.dialog.mode') }}</legend>
          <label
            v-for="option in listing.modes"
            :key="option"
            class="import-dialog__mode"
            :data-testid="`import-mode-${option}`"
          >
            <input v-model="mode" type="radio" name="import-mode" :value="option" />
            <span class="item-list__main">
              <span>{{ t(`libraryImport.modes.${option}`) }}</span>
              <span class="text-muted item-list__sub">
                {{ t(`libraryImport.modeHints.${option}`) }}
              </span>
            </span>
          </label>
        </fieldset>
        <q-checkbox
          v-if="mode && REFERENCED_MODES.includes(mode)"
          v-model="tagWrites"
          :label="t('libraryImport.dialog.tagWrites')"
          data-testid="import-tag-writes"
        />
        <q-checkbox
          v-model="deleteReplaced"
          :label="t('libraryImport.dialog.deleteReplaced')"
          data-testid="import-delete-replaced"
        />
        <p class="text-muted import-dialog__hint">
          {{ t('libraryImport.dialog.deleteReplacedHint') }}
        </p>
      </q-card-section>
      <q-card-section v-else>
        <p class="text-muted">{{ t('libraryImport.dialog.chooseFolder') }}</p>
      </q-card-section>

      <q-card-section v-if="error">
        <p class="form-error" role="alert" data-testid="import-dialog-error">
          <q-icon name="info" aria-hidden="true" />{{ t(`libraryImport.errors.${error}`) }}
        </p>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat no-caps :label="t('libraryImport.dialog.cancel')" @click="open = false" />
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="manage_search"
          :label="t('libraryImport.dialog.scan')"
          :disable="!listing?.path || !mode"
          :loading="starting"
          data-testid="import-scan"
          @click="scan"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';

import { REFERENCED_MODES, type ImportMode } from '../imports';

type ErrorCode =
  'import_running' | 'outside_roots' | 'not_a_folder' | 'mode_not_possible' | 'failed';

const open = defineModel<boolean>({ required: true });
const emit = defineEmits<{ started: [importId: string] }>();
const { t } = useI18n();

const listing = ref<Schemas['FolderListing'] | null>(null);
const mode = ref<ImportMode | null>(null);
const tagWrites = ref(false);
// ADR 0021: replaced managed originals are deleted after verification unless unchecked.
const deleteReplaced = ref(true);
const starting = ref(false);
const error = ref<ErrorCode | null>(null);

function errorCode(failed: unknown): ErrorCode {
  const detail = (failed as { detail?: unknown } | undefined)?.detail;
  const known: ErrorCode[] = [
    'import_running',
    'outside_roots',
    'not_a_folder',
    'mode_not_possible',
  ];
  return known.includes(detail as ErrorCode) ? (detail as ErrorCode) : 'failed';
}

async function browse(path: string | null | undefined): Promise<void> {
  error.value = null;
  const { data, error: failed } = await getServices().api.GET('/api/v1/library-import/folders', {
    params: { query: path ? { path } : {} },
  });
  if (failed || !data) {
    error.value = errorCode(failed);
    return;
  }
  listing.value = data;
  mode.value = data.default_mode ?? null;
  tagWrites.value = false;
}

async function scan(): Promise<void> {
  if (!listing.value?.path || !mode.value) return;
  starting.value = true;
  error.value = null;
  try {
    const { data, error: failed } = await getServices().api.POST('/api/v1/library-imports', {
      body: {
        path: listing.value.path,
        mode: mode.value,
        allow_tag_writes: REFERENCED_MODES.includes(mode.value) && tagWrites.value,
        delete_replaced: deleteReplaced.value,
      },
    });
    if (failed || !data) {
      error.value = errorCode(failed);
      return;
    }
    emit('started', data.import_id);
    open.value = false;
  } finally {
    starting.value = false;
  }
}
</script>

<style scoped>
.import-dialog {
  width: min(640px, 100vw);
  max-width: 100%;
}

.import-dialog__path {
  margin: 0;
  overflow-wrap: anywhere;
}

.import-dialog__folders {
  max-height: 40vh;
  overflow-y: auto;
}

.import-dialog__folder {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: 0;
  background: none;
  border: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.import-dialog__modes {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: none;
}

.import-dialog__legend {
  margin-bottom: var(--space-2);
  font-weight: var(--weight-medium);
}

.import-dialog__mode {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  min-height: 44px;
  cursor: pointer;
}

.import-dialog__hint {
  margin: 0;
  font-size: var(--text-sm);
}

.import-dialog__mode input {
  margin-top: 4px;
}
</style>
