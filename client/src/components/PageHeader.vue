<template>
  <header class="page-header">
    <h1 class="page-header__title">{{ title }}</h1>
    <p v-if="description" class="page-header__description">{{ description }}</p>
  </header>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>

<style scoped>
.page-header {
  margin-bottom: var(--space-6);
}

.page-header__title {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: var(--weight-bold);
  line-height: 1.2;
}

.page-header__description {
  margin: var(--space-2) 0 0;
  max-width: 60ch;
  color: var(--color-text-muted);
}
</style>
