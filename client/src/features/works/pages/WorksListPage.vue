<template>
  <q-page class="page">
    <PageHeader :title="t('pages.works.title')" :description="t('pages.works.description')" />
    <section class="library-section">
      <div class="works__bar">
        <nav class="works__types" :aria-label="t('works.filter')">
          <router-link
            v-for="option in options"
            :key="option.value"
            :to="{ name: 'works', query: option.value ? { type: option.value } : {} }"
            class="works__type"
            :class="{ 'works__type--active': option.value === type }"
            :aria-current="option.value === type ? 'page' : undefined"
            :data-testid="`works-type-${option.value || 'all'}`"
          >
            {{ option.label }}
            <span class="mono text-muted">{{
              number(counters[option.value || 'all'] ?? null)
            }}</span>
          </router-link>
        </nav>
        <router-link :to="{ name: 'persons' }" class="works__persons" data-testid="works-persons">
          <q-icon name="people" aria-hidden="true" /> {{ t('works.persons.title') }}
        </router-link>
        <q-btn
          v-if="auth.canEdit"
          unelevated
          no-caps
          color="primary"
          icon="add"
          :label="t('works.create')"
          data-testid="work-create"
          @click="creating = true"
        />
      </div>
      <LibraryList
        ref="list"
        :key="type"
        stream="works.list"
        :params="type ? { type } : {}"
        :position-key="`works:${type}`"
        :label="t('pages.works.title')"
        :empty="t('works.empty')"
      >
        <template #default="{ row }">
          <WorkRow :work="row as unknown as WorkRowData" />
        </template>
      </LibraryList>
      <WorkEditor :open="creating" @close="creating = false" @saved="opened" />
    </section>
  </q-page>
</template>

<script setup lang="ts">
import type { WorkRow as WorkRowData } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import PageHeader from '@/components/PageHeader.vue';
import LibraryList from '@/features/library/components/LibraryList.vue';
import { useCounts } from '@/features/library/numbers';
import { useAuthStore } from '@/features/users/store';

import { WORK_TYPES } from '../api';
import WorkEditor from '../components/WorkEditor.vue';
import WorkRow from '../components/WorkRow.vue';

/** All works by title, filtered by type, with the counts per type first (spec: works,
 * Works list). */
const { t } = useI18n();
const { number } = useCounts();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const creating = ref(false);
const list = ref<InstanceType<typeof LibraryList> | null>(null);

const type = computed(() => {
  const value = String(route.query.type ?? '');
  return (WORK_TYPES as string[]).includes(value) ? value : '';
});
const options = computed(() => [
  { value: '', label: t('works.all') },
  ...WORK_TYPES.map((value) => ({ value, label: t(`works.plural.${value}`) })),
]);
const counters = computed<Record<string, number>>(
  () => (list.value?.subscription.counters as Record<string, number> | undefined) ?? {},
);

function opened(workId: string): void {
  creating.value = false;
  void router.push({ name: 'work', params: { workId } });
}
</script>

<style scoped>
.works__bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-3);
}

.works__types {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.works__type,
.works__persons {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  color: inherit;
  text-decoration: none;
}

.works__type--active {
  background: var(--color-selection-bg);
}
</style>
