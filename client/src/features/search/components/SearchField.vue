<template>
  <form role="search" class="search-field" @submit.prevent="go(true)">
    <q-input
      v-model="text"
      dense
      outlined
      clearable
      type="search"
      :label="t('search.label')"
      :placeholder="t('search.placeholder')"
      autocomplete="off"
      data-testid="search-input"
      @update:model-value="schedule"
      @clear="schedule"
    >
      <template #prepend><q-icon name="search" aria-hidden="true" /></template>
    </q-input>
  </form>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

/** The search field of the Local view: searches while typing (spec: search, Search as you
 * type); the search page keeps its text, context and type in the address. */
const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const DEBOUNCE_MS = 150;

const routeText = () => (route.name === 'search' ? String(route.query.q ?? '') : '');
const text = ref(routeText());
let timer: ReturnType<typeof setTimeout> | null = null;

// Chips change the text in the address; follow them.
watch(routeText, (value) => {
  if (value !== (text.value ?? '')) text.value = value;
});

function schedule(): void {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => go(false), DEBOUNCE_MS);
}

function go(submitted: boolean): void {
  if (timer) clearTimeout(timer);
  timer = null;
  const q = (text.value ?? '').trim();
  if (route.name === 'search') {
    if (q === String(route.query.q ?? '')) return;
    void router.replace({ name: 'search', query: { ...route.query, q } });
  } else if (q || submitted) {
    void router.push({ name: 'search', query: { q } });
  }
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
});
</script>

<style scoped>
.search-field {
  margin-bottom: var(--space-3);
}
</style>
