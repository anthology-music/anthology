<template>
  <section class="settings-section" aria-labelledby="my-devices-title">
    <h2 id="my-devices-title" class="settings-section__title">
      {{ t('devices.title') }}
      <span v-if="subscription.total !== null" class="mono text-muted">
        {{ subscription.total }}
      </span>
    </h2>
    <ul class="item-list">
      <li v-for="device in devices" :key="device.id" class="item-list__row">
        <q-icon :name="icons[device.type] ?? 'devices'" size="20px" aria-hidden="true" />
        <div class="item-list__main">
          <span>{{ device.name }}</span>
          <span class="text-muted item-list__sub">
            {{ t('devices.lastUsed', { date: formatDate(device.last_used_at) }) }}
          </span>
        </div>
        <span v-if="device.current" class="badge">{{ t('devices.current') }}</span>
        <q-btn
          v-else
          flat
          no-caps
          :label="t('devices.signOut')"
          :aria-label="t('devices.signOutNamed', { name: device.name })"
          @click="signOut(device.id)"
        />
      </li>
    </ul>
    <p v-if="error" class="form-error" role="alert">
      <q-icon name="error_outline" aria-hidden="true" />{{ t('auth.errors.failed') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

interface DeviceRow {
  id: string;
  name: string;
  type: string;
  last_used_at: string | null;
  current: boolean;
}

const { t, locale } = useI18n();
const subscription = useSubscription('me.devices');
const error = ref(false);
const icons: Record<string, string> = {
  web: 'language',
  desktop: 'computer',
  mobile: 'smartphone',
};

const devices = computed(
  () =>
    [...subscription.value.rows.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, row]) => row) as unknown as DeviceRow[],
);

function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(value),
      )
    : '–';
}

async function signOut(deviceId: string) {
  error.value = false;
  const { error: failed } = await getServices().api.DELETE('/api/v1/me/devices/{device_id}', {
    params: { path: { device_id: deviceId } },
  });
  error.value = Boolean(failed);
}
</script>
