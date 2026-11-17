<template>
  <q-dialog :model-value="open" @update:model-value="(value) => !value && emit('close')">
    <q-card class="work-editor" data-testid="work-editor">
      <form @submit.prevent="save">
        <q-card-section>
          <h2 class="work-editor__title">
            {{ work ? t('works.edit') : t('works.create') }}
          </h2>
          <div class="work-editor__fields">
            <q-input
              v-model="title"
              dense
              outlined
              autofocus
              :label="t('works.fields.title')"
              data-testid="work-title"
            />
            <q-select
              v-model="type"
              dense
              outlined
              emit-value
              map-options
              :options="typeOptions"
              :label="t('works.fields.type')"
              data-testid="work-type"
            />
            <q-input
              v-model="instrumentation"
              dense
              outlined
              :label="t('works.fields.instrumentation')"
              data-testid="work-instrumentation"
            />
            <q-input
              v-model="grade"
              dense
              outlined
              :label="t('works.fields.grade')"
              data-testid="work-grade"
            />
            <q-input
              v-model="duration"
              dense
              outlined
              :label="t('works.fields.duration')"
              :hint="t('works.durationHint')"
              :error="durationInvalid"
              data-testid="work-duration"
            />
            <q-input v-model="iswc" dense outlined :label="t('works.fields.iswc')" />
          </div>
        </q-card-section>
        <q-card-section>
          <h3 class="work-editor__subtitle">{{ t('works.credits') }}</h3>
          <ul class="work-editor__credits">
            <li v-for="(credit, index) in credits" :key="credit.key" class="work-editor__credit">
              <q-select
                v-model="credit.role"
                dense
                outlined
                emit-value
                map-options
                :options="roleOptions"
                :aria-label="t('works.fields.role')"
                class="work-editor__role"
              />
              <q-select
                v-model="credit.person"
                dense
                outlined
                use-input
                hide-selected
                fill-input
                input-debounce="0"
                new-value-mode="add-unique"
                option-label="name"
                option-value="name"
                :options="personOptions"
                :label="t('works.fields.person')"
                class="work-editor__person"
                :data-testid="`credit-person-${index}`"
                @filter="filterPersons"
                @new-value="
                  (name: string, done: (value: Person) => void) => done({ id: null, name })
                "
              />
              <q-btn
                flat
                round
                dense
                icon="close"
                :aria-label="t('works.removeCredit')"
                @click="credits.splice(index, 1)"
              />
            </li>
          </ul>
          <q-btn
            flat
            no-caps
            icon="person_add"
            :label="t('works.addCredit')"
            data-testid="credit-add"
            @click="addCredit"
          />
        </q-card-section>
        <q-card-section v-if="problem" class="work-editor__problem" role="alert">
          {{ t(`works.problem.${problem}`) }}
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('works.cancel')" @click="emit('close')" />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            :disable="!title.trim() || durationInvalid"
            :loading="busy"
            :label="t('works.save')"
            data-testid="work-save"
          />
        </q-card-actions>
      </form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { PersonRow, WorkDetailRow } from '@anthology/api-types';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { useSubscription } from '@/sync/useSubscription';

import {
  CREDIT_ROLES,
  type CreditIn,
  type CreditRole,
  createWork,
  setCredits,
  updateWork,
  WORK_TYPES,
  type WorkProblem,
  type WorkType,
} from '../api';
import { formatDuration, parseDuration } from '../duration';

/** Create a work or edit one (``work``): fields and credits. A credit names an existing
 * person (picked from the list) or a new one by name (spec: works, Persons). */
const props = defineProps<{ open: boolean; work?: WorkDetailRow | null }>();
const emit = defineEmits<{ close: []; saved: [workId: string] }>();

interface Person {
  id: string | null;
  name: string;
}
interface Credit {
  key: number;
  role: CreditRole;
  person: Person | null;
}

const { t } = useI18n();
const title = ref('');
const type = ref<WorkType>('original');
const instrumentation = ref('');
const grade = ref('');
const duration = ref('');
const iswc = ref('');
const credits = ref<Credit[]>([]);
const busy = ref(false);
const problem = ref<WorkProblem | null>(null);
let keys = 0;

const typeOptions = WORK_TYPES.map((value) => ({ value, label: t(`works.types.${value}`) }));
const roleOptions = CREDIT_ROLES.map((value) => ({ value, label: t(`works.roles.${value}`) }));
const durationInvalid = computed(() => parseDuration(duration.value) === undefined);

// Persons to pick from: the first ones of the list, filtered while typing.
const persons = useSubscription('works.persons', {}, [0, 500]);
const filter = ref('');
const personOptions = computed(() => {
  const needle = filter.value.toLowerCase();
  const rows = [...persons.value.rows.values()] as unknown as PersonRow[];
  return rows
    .filter((row) => !needle || row.name.toLowerCase().includes(needle))
    .slice(0, 50)
    .map((row) => ({ id: row.id, name: row.name }));
});

function filterPersons(value: string, update: (callback: () => void) => void): void {
  update(() => {
    filter.value = value;
  });
}

function addCredit(): void {
  credits.value.push({ key: keys++, role: 'composer', person: null });
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    problem.value = null;
    const work = props.work;
    title.value = work?.title ?? '';
    type.value = work?.type ?? 'original';
    instrumentation.value = work?.instrumentation ?? '';
    grade.value = work?.grade ?? '';
    duration.value = work?.duration_sec != null ? formatDuration(work.duration_sec) : '';
    iswc.value = work?.iswc ?? '';
    credits.value = (work?.credits ?? []).map((credit) => ({
      key: keys++,
      role: credit.role,
      person: { id: credit.person_id, name: credit.name },
    }));
  },
  { immediate: true },
);

function creditBody(): CreditIn[] {
  return credits.value
    .filter((credit) => credit.person && credit.person.name.trim())
    .map((credit) =>
      credit.person!.id
        ? { role: credit.role, person_id: credit.person!.id }
        : { role: credit.role, name: credit.person!.name.trim() },
    );
}

async function save(): Promise<void> {
  busy.value = true;
  const fields = {
    title: title.value.trim(),
    type: type.value,
    instrumentation: instrumentation.value.trim() || null,
    grade: grade.value.trim() || null,
    duration_sec: parseDuration(duration.value) ?? null,
    iswc: iswc.value.trim() || null,
  };
  let workId = props.work?.id ?? null;
  if (workId === null) {
    const created = await createWork({ ...fields, credits: creditBody() });
    problem.value = created.problem;
    workId = created.id;
  } else {
    problem.value = (await updateWork(workId, fields)) ?? (await setCredits(workId, creditBody()));
  }
  busy.value = false;
  if (!problem.value && workId) emit('saved', workId);
}
</script>

<style scoped>
.work-editor {
  width: min(640px, 100vw);
}

.work-editor__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-lg);
}

.work-editor__subtitle {
  margin: 0 0 var(--space-2);
  font-size: var(--text-md);
}

.work-editor__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-2);
}

.work-editor__credits {
  margin: 0;
  padding: 0;
  list-style: none;
}

.work-editor__credit {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-2);
}

.work-editor__role {
  width: 150px;
}

.work-editor__person {
  flex: 1;
}

.work-editor__problem {
  color: var(--color-status-error);
}
</style>
