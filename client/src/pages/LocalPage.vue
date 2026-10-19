<template>
  <q-page class="page local-page">
    <LibraryNav class="local-page__nav" />
    <div class="local-page__content">
      <!-- Keyed by address: another artist or release gets fresh subscriptions. -->
      <router-view :key="route.fullPath" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';

import LibraryNav from '@/features/library/components/LibraryNav.vue';

const route = useRoute();
</script>

<style scoped>
.local-page {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: var(--space-6);
  align-items: start;
}

@media (max-width: 839px) {
  .local-page {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
  }
}
</style>
