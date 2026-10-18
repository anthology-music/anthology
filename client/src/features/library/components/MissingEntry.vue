<template>
  <div class="missing-entry" role="status" data-testid="library-missing">
    <q-icon name="info" size="24px" aria-hidden="true" />
    <p>{{ message }}</p>
    <router-link :to="{ name: 'library-albums' }">{{ t('library.back') }}</router-link>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

defineProps<{ message: string }>();

const { t } = useI18n();
</script>

<style scoped>
.missing-entry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  margin-top: var(--space-6);
}

.missing-entry p {
  margin: 0;
}

.missing-entry a {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target);
  color: var(--color-accent-strong);
}
</style>
