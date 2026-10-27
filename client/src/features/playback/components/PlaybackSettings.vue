<template>
  <section class="settings-section" aria-labelledby="playback-settings-title">
    <h2 id="playback-settings-title" class="settings-section__title">
      {{ t('playback.settings.title') }}
    </h2>
    <p class="text-muted">{{ t('playback.settings.hint') }}</p>
    <fieldset class="playback-settings__options" :disabled="settings === null">
      <legend class="playback-settings__legend">{{ t('playback.settings.bitrate') }}</legend>
      <label
        v-for="option in BITRATES"
        :key="option"
        class="playback-settings__option"
        :data-testid="`bitrate-${option}`"
      >
        <input
          type="radio"
          name="audio-bitrate"
          :value="option"
          :checked="settings?.audio_bitrate === option"
          @change="save(option)"
        />
        {{ t(`playback.settings.bitrates.${option}`) }}
      </label>
    </fieldset>
    <p
      v-if="message"
      class="playback-settings__message"
      role="status"
      data-testid="bitrate-message"
    >
      <q-icon :name="message === 'saved' ? 'check_circle' : 'error'" aria-hidden="true" />
      {{ t(`playback.settings.${message}`) }}
    </p>
  </section>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';

type DeviceSettings = Schemas['DeviceSettingsData'];
type Bitrate = DeviceSettings['audio_bitrate'];

/** "Bitrate on this device" (spec: transcoding, Bitrate per user and device). */
const BITRATES: Bitrate[] = ['original', '320', '256', '192', '128'];

const { t } = useI18n();
const settings = ref<DeviceSettings | null>(null);
const message = ref<'saved' | 'failed' | null>(null);

onMounted(async () => {
  const { data } = await getServices().api.GET('/api/v1/me/device-settings');
  settings.value = data ?? null;
});

async function save(bitrate: Bitrate): Promise<void> {
  if (!settings.value) return;
  const previous = settings.value;
  settings.value = { ...previous, audio_bitrate: bitrate };
  const { data, error } = await getServices().api.PUT('/api/v1/me/device-settings', {
    body: settings.value,
  });
  if (error || !data) {
    settings.value = previous;
    message.value = 'failed';
    return;
  }
  settings.value = data;
  message.value = 'saved';
}
</script>

<style scoped>
.playback-settings__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  border: 0;
}

.playback-settings__legend {
  margin-bottom: var(--space-2);
  font-weight: var(--weight-medium);
}

.playback-settings__option {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target);
}
</style>
