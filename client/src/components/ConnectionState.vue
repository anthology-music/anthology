<template>
  <div class="connection" role="status" :data-state="state">
    <span class="connection__dot" aria-hidden="true" />
    {{ t(`connection.${state}`) }}
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import type { ConnectionState } from '@/sync/connection';

withDefaults(defineProps<{ state?: ConnectionState }>(), { state: 'offline' });

const { t } = useI18n();
</script>

<style scoped>
.connection {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.connection__dot {
  width: var(--space-2);
  height: var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--color-status-waiting);
}

.connection[data-state='live'] .connection__dot {
  background: var(--color-status-ok);
}

.connection[data-state='outdated'] .connection__dot {
  background: var(--color-status-error);
}

.connection[data-state='connecting'] .connection__dot,
.connection[data-state='reconnecting'] .connection__dot {
  background: var(--color-status-running);
}
</style>
