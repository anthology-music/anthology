<template>
  <router-link
    :to="{ name: 'work', params: { workId: work.id } }"
    class="work-row"
    :data-testid="`work-${work.title}`"
  >
    <q-icon :name="WORK_ICONS[work.type]" class="work-row__icon" aria-hidden="true" />
    <span class="work-row__main">
      <span class="work-row__title">{{ work.title }}</span>
      <span class="text-muted work-row__sub">
        {{ t(`works.types.${work.type}`) }}
        <template v-if="work.composers.length"> · {{ work.composers.join(', ') }}</template>
        <template v-if="work.arrangers.length">
          · {{ t('works.arrangedBy', { names: work.arrangers.join(', ') }) }}
        </template>
      </span>
    </span>
    <span v-if="work.grade" class="mono text-muted work-row__grade">
      {{ t('works.gradeShort', { grade: work.grade }) }}
    </span>
  </router-link>
</template>

<script setup lang="ts">
import type { WorkRow } from '@anthology/api-types';
import { useI18n } from 'vue-i18n';

import { WORK_ICONS } from '../icons';

/** A work in a list: title, type, composers and arrangers, grade. */
defineProps<{ work: WorkRow }>();

const { t } = useI18n();
</script>

<style scoped>
.work-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target);
  padding: var(--space-1) var(--space-2);
  color: inherit;
  text-decoration: none;
}

.work-row:hover,
.work-row:focus-visible {
  background: var(--color-surface-raised);
}

.work-row__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.work-row__title,
.work-row__sub {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.work-row__sub {
  font-size: var(--text-sm);
}
</style>
