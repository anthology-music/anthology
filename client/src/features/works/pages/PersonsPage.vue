<template>
  <q-page class="page">
    <section class="library-section">
      <LibraryBreadcrumb
        :items="[
          { label: t('pages.works.title'), to: { name: 'works' } },
          { label: t('works.persons.title') },
        ]"
      />
      <h1 class="library-section__title">{{ t('works.persons.title') }}</h1>
      <LibraryList
        stream="works.persons"
        position-key="works-persons"
        :label="t('works.persons.title')"
        :empty="t('works.persons.empty')"
      >
        <template #default="{ row }">
          <router-link
            :to="{ name: 'person', params: { personId: String(row.id) } }"
            class="persons__row"
            :data-testid="`person-${String(row.name)}`"
          >
            <q-icon name="person" aria-hidden="true" />
            <span class="persons__name">{{ row.name }}</span>
            <span class="text-muted">{{
              t('works.persons.works', { n: Number(row.work_count) })
            }}</span>
          </router-link>
        </template>
      </LibraryList>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import LibraryBreadcrumb from '@/features/library/components/LibraryBreadcrumb.vue';
import LibraryList from '@/features/library/components/LibraryList.vue';

/** Composers, lyricists and arrangers by name (spec: works, Persons). */
const { t } = useI18n();
</script>

<style scoped>
.persons__row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  min-height: var(--touch-target);
  padding: 0 var(--space-2);
  color: inherit;
  text-decoration: none;
}

.persons__name {
  flex: 1;
}
</style>
