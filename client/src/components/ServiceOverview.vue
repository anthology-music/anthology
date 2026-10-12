<template>
  <section class="settings-section" aria-labelledby="services-title">
    <h2 id="services-title" class="settings-section__title">{{ t('services.title') }}</h2>
    <ul class="item-list">
      <li
        v-for="service in services"
        :key="service.id"
        class="item-list__row"
        :data-testid="`service-${service.name}`"
      >
        <div class="item-list__main">
          <span>{{ t(`services.names.${service.name}`, service.name) }}</span>
          <span class="text-muted item-list__sub mono">
            <template v-if="service.version">
              {{ t('services.versions', { version: service.version, api: service.interface }) }}
            </template>
            <template v-else-if="service.message">{{ service.message }}</template>
          </span>
        </div>
        <span class="service-status" :data-status="service.status">
          <q-icon :name="icons[service.status]" size="18px" aria-hidden="true" />
          <span class="service-status__text">{{ t(`services.status.${service.status}`) }}</span>
        </span>
      </li>
      <li v-if="services.length === 0" class="item-list__row text-muted">
        {{ t('services.none') }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import { useServices, type ServiceState } from '@/sync/services';

const { t } = useI18n();
const services = useServices();

const icons: Record<ServiceState, string> = {
  available: 'check_circle',
  unavailable: 'error',
  incompatible: 'warning',
};
</script>

<style scoped>
.service-status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  white-space: nowrap;
}

.service-status[data-status='available'] {
  color: var(--color-status-ok);
}

.service-status[data-status='unavailable'] {
  color: var(--color-status-error);
}

.service-status[data-status='incompatible'] {
  color: var(--color-status-warning);
}
</style>
