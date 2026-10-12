<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="auth-page">
        <div class="auth-card">
          <div class="auth-card__brand">
            <q-icon name="library_music" size="28px" aria-hidden="true" />
            <span>{{ t('app.name') }}</span>
          </div>
          <router-view />
        </div>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
</script>

<style scoped>
.auth-page {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
}

.auth-card {
  width: 100%;
  max-width: 400px;
  padding: var(--space-8);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.auth-card__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
  font-size: var(--text-lg);
  font-weight: var(--weight-bold);
  color: var(--color-accent-strong);
}
</style>
