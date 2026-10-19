<template>
  <nav class="breadcrumb" :aria-label="t('library.path')">
    <ol>
      <li v-for="(item, index) in items" :key="index">
        <router-link v-if="item.to && index < items.length - 1" :to="item.to">
          {{ item.label }}
        </router-link>
        <span v-else aria-current="page">{{ item.label }}</span>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { RouteLocationRaw } from 'vue-router';

defineProps<{ items: { label: string; to?: RouteLocationRaw }[] }>();

const { t } = useI18n();
</script>

<style scoped>
.breadcrumb ol {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.breadcrumb li + li::before {
  content: '›';
  margin-right: var(--space-2);
}

.breadcrumb a {
  color: var(--color-text-secondary);
}

.breadcrumb [aria-current] {
  color: var(--color-text);
}
</style>
