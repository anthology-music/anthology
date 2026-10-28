<template>
  <div v-if="downloads.notice" class="download-notice" role="status" data-testid="download-notice">
    <q-icon name="info" aria-hidden="true" />
    <span>{{ t(`library.download.${downloads.notice}`) }}</span>
    <q-btn
      flat
      round
      size="sm"
      icon="close"
      :aria-label="t('library.download.dismiss')"
      data-testid="download-notice-close"
      @click="downloads.dismiss()"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import { useDownloadStore } from '../downloads';

const { t } = useI18n();
const downloads = useDownloadStore();
</script>

<style scoped>
.download-notice {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  border-top: 1px solid var(--color-border);
}
</style>
