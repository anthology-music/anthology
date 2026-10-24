<template>
  <q-dialog :model-value="open" @update:model-value="emit('close')">
    <q-card class="tag-editor" data-testid="tag-editor">
      <form @submit.prevent="save">
        <q-card-section>
          <h2 class="settings-section__title">
            {{ mode === 'release' ? t('tagging.editRelease') : t('tagging.editTags') }}
          </h2>
          <p class="text-muted tag-editor__count" data-testid="tag-editor-count">
            {{ t('tagging.appliesTo', { n: number(count) }, count) }}
          </p>
          <p v-if="loading" class="text-muted">{{ t('tagging.loading') }}</p>
          <div v-else class="tag-editor__fields">
            <label v-for="field in visibleFields" :key="field.key" class="tag-editor__field">
              <span>{{ t(`tagging.fields.${field.name}`) }}</span>
              <input
                v-model="state(field.key).text"
                :type="field.kind === 'number' ? 'number' : 'text'"
                :placeholder="state(field.key).mixed ? t('tagging.mixed') : ''"
                :class="{ 'tag-editor__input--dirty': state(field.key).dirty }"
                :data-testid="`tag-field-${field.name}`"
                @input="state(field.key).dirty = true"
              />
              <span v-if="field.kind === 'list'" class="text-muted tag-editor__hint">
                {{ t('tagging.listHint') }}
              </span>
            </label>
          </div>
          <p v-if="error" class="form-error" role="alert" data-testid="tag-editor-error">
            <q-icon name="error" aria-hidden="true" />{{ error }}
          </p>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('tagging.cancel')" @click="emit('close')" />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            :disable="saving || !dirty"
            :label="t('tagging.apply')"
            data-testid="tag-editor-apply"
          />
        </q-card-actions>
      </form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useCounts } from '@/features/library/numbers';
import { getServices } from '@/services';

import type { TrackSelection } from '../selection';

type Level = 'recording' | 'release' | 'track';
type Kind = 'text' | 'number' | 'list';
interface FieldSpec {
  level: Level;
  name: string;
  kind: Kind;
  key: string;
}
interface FieldState {
  text: string;
  mixed: boolean;
  dirty: boolean;
}

export type EditResult = { kind: 'saved'; changed: number } | { kind: 'job'; items: number };

/**
 * The tag editor (mockup Lokal-Editieren): the fields of the selected tracks, mixed values
 * shown as such; only edited fields are sent. `release` edits the album's own fields.
 */
const props = defineProps<{
  open: boolean;
  selection: TrackSelection;
  count: number;
  mode: 'tracks' | 'release';
}>();
const emit = defineEmits<{ close: []; done: [result: EditResult] }>();

const { t } = useI18n();
const { number } = useCounts();

const spec = (level: Level, name: string, kind: Kind = 'text'): FieldSpec => ({
  level,
  name,
  kind,
  key: `${level}.${name}`,
});
const TRACK_FIELDS: FieldSpec[] = [
  spec('recording', 'title'),
  spec('recording', 'artist'),
  spec('track', 'album'),
  spec('track', 'album_artist'),
  spec('release', 'year', 'number'),
  spec('recording', 'genres', 'list'),
  spec('recording', 'composers', 'list'),
  spec('release', 'label'),
  spec('recording', 'isrc'),
  spec('recording', 'mb_recording_id'),
  spec('track', 'track_number', 'number'),
  spec('track', 'disc_number', 'number'),
];
const RELEASE_FIELDS: FieldSpec[] = [
  spec('release', 'title'),
  spec('release', 'album_artist'),
  spec('release', 'year', 'number'),
  spec('release', 'label'),
];
// Positions make sense for one track only.
const SINGLE_ONLY = new Set(['track.track_number', 'track.disc_number']);

const fields = computed(() => (props.mode === 'release' ? RELEASE_FIELDS : TRACK_FIELDS));
const visibleFields = computed(() =>
  fields.value.filter((field) => props.count === 1 || !SINGLE_ONLY.has(field.key)),
);
const form = reactive<Record<string, FieldState>>({});
const state = (key: string): FieldState => (form[key] ??= { text: '', mixed: false, dirty: false });
const loading = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);
const dirty = computed(() => visibleFields.value.some((field) => form[field.key]?.dirty));

function text(value: unknown, kind: Kind): string {
  if (value === null || value === undefined) return '';
  if (kind === 'list') return (value as string[]).join(', ');
  if (typeof value === 'string') return value;
  return typeof value === 'number' || typeof value === 'boolean'
    ? value.toString()
    : JSON.stringify(value);
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  for (const field of fields.value) form[field.key] = { text: '', mixed: false, dirty: false };
  try {
    const { data } = await getServices().api.POST('/api/v1/tagging/values', {
      body: props.selection,
    });
    if (!data) return;
    for (const field of fields.value) {
      const value = data.fields[field.level]?.[field.name];
      if (!value) continue;
      form[field.key] = {
        text: value.mixed ? '' : text(value.value, field.kind),
        mixed: value.mixed ?? false,
        dirty: false,
      };
    }
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void load();
  },
  { immediate: true },
);

function value(field: FieldSpec, raw: string | number): unknown {
  // Number inputs give numbers.
  const trimmed = String(raw).trim();
  if (field.kind === 'list') {
    return trimmed
      ? trimmed
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean)
      : [];
  }
  if (field.kind === 'number') return trimmed ? Number(trimmed) : null;
  return trimmed || null;
}

async function save(): Promise<void> {
  const changes: Partial<Record<Level, Record<string, unknown>>> = {};
  for (const field of visibleFields.value) {
    const state = form[field.key];
    if (!state?.dirty) continue;
    (changes[field.level] ??= {})[field.name] = value(field, state.text);
  }
  saving.value = true;
  error.value = null;
  try {
    const {
      data,
      error: failure,
      response,
    } = await getServices().api.POST('/api/v1/tagging/edits', {
      body: {
        ...props.selection,
        fields: changes as Record<Level, Record<string, unknown>>,
        preview: false,
      },
    });
    if (data) {
      emit(
        'done',
        data.job_id
          ? { kind: 'job', items: data.items }
          : { kind: 'saved', changed: data.changed ?? 0 },
      );
      emit('close');
      return;
    }
    const detail = (failure as { detail?: unknown } | undefined)?.detail;
    error.value =
      response.status === 409 && detail === 'duplicate_id'
        ? t('tagging.errors.duplicate_id')
        : response.status === 422
          ? t('tagging.errors.invalid', { detail: typeof detail === 'string' ? detail : '' })
          : t('tagging.errors.failed');
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.tag-editor {
  width: min(560px, 100vw - 32px);
}

.tag-editor__count {
  margin: 0 0 var(--space-3);
}

.tag-editor__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
}

.tag-editor__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.tag-editor__field input {
  min-height: var(--touch-target);
  padding: 0 var(--space-2);
  color: var(--color-text);
  font-size: var(--text-md);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.tag-editor__input--dirty {
  border-color: var(--color-accent) !important;
}

.tag-editor__hint {
  font-size: var(--text-xs);
}
</style>
