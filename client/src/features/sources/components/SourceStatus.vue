<template>
  <q-btn
    flat
    no-caps
    icon="info"
    :label="t('sources.status.open')"
    data-testid="source-status-open"
    @click="open = true"
  />
  <q-dialog v-model="open">
    <q-card class="source-status" data-testid="source-status">
      <q-card-section>
        <h2 class="source-status__title">{{ t('sources.status.title') }}</h2>
        <p v-if="!shown.length" class="text-muted">{{ t('sources.status.none') }}</p>
        <ul v-else class="source-status__list">
          <li
            v-for="service in shown"
            :key="service.id"
            class="source-status__item"
            :data-testid="`source-status-${service.id}`"
          >
            <q-icon
              :name="service.available ? 'check_circle' : 'error'"
              :class="service.available ? 'source-status__ok' : 'source-status__problem'"
              aria-hidden="true"
            />
            <span class="source-status__name">
              {{ service.name }}
              <span v-if="service.version" class="mono text-muted">{{ service.version }}</span>
            </span>
            <span>
              {{
                service.available
                  ? t('sources.status.available')
                  : t(`sources.problems.${service.problem ?? 'unreachable'}`)
              }}
            </span>
          </li>
        </ul>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn v-close-popup flat no-caps :label="t('sources.status.close')" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { SourceServiceRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useSourceServices } from '../services';

/** Why a source is missing, for every user, only when opened (spec: Source status). Without
 * ``services`` it subscribes to them itself. */
const props = defineProps<{ services?: SourceServiceRow[] }>();

const { t } = useI18n();
const open = ref(false);
const own = props.services === undefined ? useSourceServices().all : null;
const shown = computed(() => props.services ?? own?.value ?? []);
</script>

<style scoped>
.source-status {
  min-width: min(480px, 90vw);
}

.source-status__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-lg);
  font-weight: var(--weight-medium);
}

.source-status__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-status__item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target);
}

.source-status__ok {
  color: var(--color-status-ok);
}

.source-status__problem {
  color: var(--color-status-error);
}
</style>
