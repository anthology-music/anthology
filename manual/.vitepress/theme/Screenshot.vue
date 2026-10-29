<template>
  <figure class="screenshot">
    <img v-if="available" :src="src" :alt="alt" loading="lazy" @error="available = false" />
    <div v-else class="screenshot__placeholder" role="img" :aria-label="alt">
      {{ de ? 'Bildschirmfoto' : 'Screenshot' }}: {{ name }}
    </div>
    <figcaption v-if="caption">{{ caption }}</figcaption>
  </figure>
</template>

<script setup lang="ts">
import { useData, withBase } from 'vitepress';
import { computed, ref } from 'vue';

/**
 * A screenshot of the app by its stable name, taken by the walkthrough tests in the page's
 * language (manual/walkthrough). Builds without screenshots show a placeholder.
 */
const props = defineProps<{ name: string; alt: string; caption?: string }>();
const { lang } = useData();
const de = computed(() => lang.value === 'de');
const available = ref(true);
const src = computed(() => withBase(`/screenshots/${de.value ? 'de' : 'en'}/${props.name}.png`));
</script>

<style scoped>
.screenshot {
  margin: 16px 0;
}

.screenshot img {
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
}

.screenshot__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  border: 1px dashed var(--vp-c-divider);
  border-radius: 8px;
  color: var(--vp-c-text-2);
  font-size: 14px;
}

figcaption {
  margin-top: 4px;
  color: var(--vp-c-text-2);
  font-size: 13px;
}
</style>
