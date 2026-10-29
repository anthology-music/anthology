<template>
  <div v-if="!manualVersion" class="unreleased" role="note">
    {{
      de
        ? 'Dieses Handbuch beschreibt den unveröffentlichten Stand von main.'
        : 'This manual describes the unreleased state of main.'
    }}
  </div>
  <div v-else-if="prerelease" class="unreleased" role="note">
    {{
      de
        ? `Anthology ${manualVersion} ist eine Vorabversion – noch nicht für den produktiven Einsatz gedacht.`
        : `Anthology ${manualVersion} is a pre-release – not meant for production use yet.`
    }}
  </div>
</template>

<script setup lang="ts">
import { useData } from 'vitepress';
import { computed } from 'vue';

import { manualVersion } from './build';

const { lang } = useData();
const de = computed(() => lang.value === 'de');
const prerelease = /^v?0\.|-/.test(manualVersion);
</script>

<style scoped>
.unreleased {
  margin: 0 0 16px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--vp-c-warning-soft);
  font-size: 14px;
}
</style>
