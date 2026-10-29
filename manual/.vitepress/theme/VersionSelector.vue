<template>
  <label class="version-selector">
    <span class="visually-hidden">{{ de ? 'Version des Handbuchs' : 'Manual version' }}</span>
    <select :value="current" @change="go(($event.target as HTMLSelectElement).value)">
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </label>
</template>

<script setup lang="ts">
import { useData } from 'vitepress';
import { computed } from 'vue';

import { manualVersion, siteRoot } from './build';
import { useVersions } from './versions';

/** Every published release and the development state (versions.json). */
const { lang } = useData();
const de = computed(() => lang.value === 'de');
const versions = useVersions(siteRoot);
const own = manualVersion ? manualVersion.replace(/^v(\d+\.\d+).*$/, 'v$1') : 'next';

const options = computed(() => {
  const list = (versions.value?.releases ?? []).map((release) => ({
    value: `${release.path}/`,
    label:
      release.tag +
      (release.path === versions.value?.latest ? (de.value ? ' (aktuell)' : ' (latest)') : ''),
  }));
  if (versions.value?.next ?? !manualVersion)
    list.push({ value: 'next/', label: de.value ? 'Entwicklung (main)' : 'Development (main)' });
  if (!list.some((option) => option.value === `${own}/`))
    list.unshift({ value: `${own}/`, label: manualVersion || 'main' });
  return list;
});
const current = computed(() => `${own}/`);

function go(directory: string): void {
  const page = window.location.pathname.replace(/^.*?\/(v\d+\.\d+|next)\//, '');
  window.location.href = `${siteRoot}${directory}${de.value && !page.startsWith('de/') ? 'de/' : ''}${page}`;
}
</script>

<style scoped>
.version-selector select {
  padding: 2px 6px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 13px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
</style>
