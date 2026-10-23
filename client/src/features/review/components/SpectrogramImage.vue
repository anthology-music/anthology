<template>
  <figure class="spectrogram" data-testid="spectrogram">
    <img v-if="url" :src="url" :alt="t('review.evidence.spectrogramAlt')" />
    <p v-else-if="failed" class="text-muted">{{ t('review.evidence.spectrogramMissing') }}</p>
    <div v-else class="spectrogram__loading" aria-busy="true" />
    <figcaption class="text-muted">{{ t('review.evidence.spectrogram') }}</figcaption>
  </figure>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';

/** The spectrogram of an audio hash, loaded over HTTP with the access token. */
const props = defineProps<{ audioHash: string }>();

const { t } = useI18n();
const url = ref<string | null>(null);
const failed = ref(false);

onMounted(async () => {
  const { data } = await getServices().api.GET(
    '/api/v1/quality-analysis/{audio_hash}/spectrogram.png',
    { params: { path: { audio_hash: props.audioHash } }, parseAs: 'blob' },
  );
  if (data) url.value = URL.createObjectURL(data);
  else failed.value = true;
});

onBeforeUnmount(() => {
  if (url.value) URL.revokeObjectURL(url.value);
});
</script>

<style scoped>
.spectrogram {
  margin: 0;
}

.spectrogram img,
.spectrogram__loading {
  display: block;
  width: 100%;
  aspect-ratio: 2 / 1;
  border-radius: var(--radius-sm);
  background: var(--color-skeleton);
}

.spectrogram figcaption {
  margin-top: var(--space-1);
  font-size: var(--text-sm);
}
</style>
