<template>
  <q-page class="page">
    <section class="library-section">
      <LibraryBreadcrumb
        :items="[
          { label: t('pages.works.title'), to: { name: 'works' } },
          { label: t('works.persons.title'), to: { name: 'persons' } },
          { label: person?.name ?? '…' },
        ]"
      />
      <MissingEntry v-if="header.total === 0" :message="t('works.persons.missing')" />
      <template v-else>
        <header class="library-header">
          <div class="library-header__text">
            <span class="text-muted library-header__kind">{{ t('works.persons.kind') }}</span>
            <h1 class="library-header__title" data-testid="person-name">
              {{ person?.name ?? '…' }}
            </h1>
            <div v-if="auth.canEdit && person" class="person-page__actions">
              <form class="person-page__form" @submit.prevent="rename">
                <q-input
                  v-model="name"
                  dense
                  outlined
                  :label="t('works.persons.rename')"
                  data-testid="person-rename"
                />
                <q-btn
                  type="submit"
                  outline
                  no-caps
                  :label="t('works.save')"
                  :disable="!name.trim()"
                />
              </form>
              <q-btn
                flat
                no-caps
                icon="merge"
                :label="t('works.persons.merge')"
                data-testid="person-merge"
                @click="merging = true"
              />
            </div>
          </div>
        </header>
        <p v-if="problem" class="person-page__problem" role="alert">
          {{ t(`works.problem.${problem}`) }}
        </p>
        <LibraryList
          stream="works.person.works"
          :params="{ person_id: personId }"
          :position-key="`person:${personId}`"
          :label="t('works.persons.worksOf', { name: person?.name ?? '' })"
          :empty="t('works.empty')"
        >
          <template #default="{ row }">
            <div class="person-page__row">
              <span class="text-muted person-page__role">{{
                t(`works.roles.${String(row.role)}`)
              }}</span>
              <WorkRow :work="(row as unknown as PersonWorkRow).work" class="person-page__work" />
            </div>
          </template>
        </LibraryList>
      </template>
      <q-dialog v-model="merging">
        <q-card class="person-page__dialog">
          <q-card-section>
            <p>{{ t('works.persons.mergeHint', { name: person?.name ?? '' }) }}</p>
            <q-select
              v-model="target"
              dense
              outlined
              use-input
              input-debounce="0"
              :options="targets"
              :label="t('works.persons.mergeInto')"
              data-testid="person-merge-target"
              @filter="filterTargets"
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn v-close-popup flat no-caps :label="t('works.cancel')" />
            <q-btn
              unelevated
              no-caps
              color="primary"
              :disable="!target"
              :label="t('works.persons.merge')"
              data-testid="person-merge-confirm"
              @click="merge"
            />
          </q-card-actions>
        </q-card>
      </q-dialog>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import type { PersonRow, PersonWorkRow } from '@anthology/api-types';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import LibraryBreadcrumb from '@/features/library/components/LibraryBreadcrumb.vue';
import LibraryList from '@/features/library/components/LibraryList.vue';
import MissingEntry from '@/features/library/components/MissingEntry.vue';
import { useAuthStore } from '@/features/users/store';
import { useSubscription } from '@/sync/useSubscription';

import { mergePerson, renamePerson, type WorkProblem } from '../api';
import WorkRow from '../components/WorkRow.vue';

/** A person's works by role; editors rename and merge (spec: works, Persons). */
const props = defineProps<{ personId: string }>();

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const header = useSubscription('works.person', { person_id: props.personId }, [0, 1]);
const person = computed(() => (header.value.rows.get(0) as unknown as PersonRow) ?? null);
const name = ref('');
const merging = ref(false);
const target = ref<{ value: string; label: string } | null>(null);
const problem = ref<WorkProblem | null>(null);

watch(person, (value) => {
  if (value && !name.value) name.value = value.name;
});

const persons = useSubscription('works.persons', {}, [0, 500]);
const filter = ref('');
const targets = computed(() =>
  ([...persons.value.rows.values()] as unknown as PersonRow[])
    .filter((row) => row.id !== props.personId)
    .filter((row) => !filter.value || row.name.toLowerCase().includes(filter.value.toLowerCase()))
    .slice(0, 50)
    .map((row) => ({ value: row.id, label: row.name })),
);

function filterTargets(value: string, update: (callback: () => void) => void): void {
  update(() => {
    filter.value = value;
  });
}

async function rename(): Promise<void> {
  problem.value = await renamePerson(props.personId, name.value.trim());
}

async function merge(): Promise<void> {
  if (!target.value) return;
  merging.value = false;
  problem.value = await mergePerson(props.personId, target.value.value);
  if (!problem.value)
    await router.replace({ name: 'person', params: { personId: target.value.value } });
}
</script>

<style scoped>
.person-page__actions,
.person-page__form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.person-page__row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.person-page__role {
  width: 10ch;
}

.person-page__work {
  flex: 1;
  min-width: 0;
}

.person-page__problem {
  color: var(--color-status-error);
}

.person-page__dialog {
  width: min(480px, 100vw);
}
</style>
