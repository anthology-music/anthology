<template>
  <section class="settings-section" aria-labelledby="output-settings-title">
    <h2 id="output-settings-title" class="settings-section__title">
      {{ t('playback.outputs.settings.title') }}
    </h2>
    <p class="text-muted">{{ t('playback.outputs.settings.hint') }}</p>
    <ul class="item-list">
      <li
        v-for="system in outputs.systems"
        :key="system.id"
        class="item-list__row"
        :data-testid="`output-system-${system.address}`"
      >
        <div class="item-list__main">
          <span>{{ system.name }}</span>
          <span class="text-muted item-list__sub">
            <span class="mono">{{ system.address }}</span> ·
            {{ t(`playback.outputs.settings.${system.origin}`) }}
            <template v-if="system.reason"> · {{ system.reason }}</template>
          </span>
        </div>
        <span class="output-state" :data-state="system.state">
          <q-icon
            :name="system.state === 'online' ? 'check_circle' : 'error'"
            size="18px"
            aria-hidden="true"
          />
          {{ t(`playback.outputs.settings.${system.state}`) }}
        </span>
        <q-btn
          v-if="auth.isAdmin && system.origin === 'manual'"
          flat
          dense
          :label="t('playback.outputs.settings.remove')"
          :data-testid="`output-system-remove-${system.address}`"
          @click="remove(system.id)"
        />
      </li>
      <li v-if="outputs.systems.length === 0" class="item-list__row text-muted">
        {{ t('playback.outputs.settings.none') }}
      </li>
    </ul>
    <form v-if="auth.isAdmin" class="output-settings__form" @submit.prevent="add">
      <q-input
        v-model="address"
        dense
        outlined
        :label="t('playback.outputs.settings.address')"
        placeholder="192.168.1.20"
        data-testid="output-address"
      />
      <q-btn
        type="submit"
        color="primary"
        unelevated
        :disable="address.trim() === ''"
        :label="t('playback.outputs.settings.add')"
        data-testid="output-address-add"
      />
    </form>
    <p v-if="problem" class="output-settings__problem" role="alert" data-testid="output-problem">
      <q-icon name="error" aria-hidden="true" /> {{ t(`playback.outputs.settings.${problem}`) }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { useAuthStore } from '@/features/users/store';

import { addSystem, removeSystem, useOutputs } from '../outputs';

/** Output systems and their state for every user; admins enter the addresses of systems the
 * server cannot discover (spec: playback, Output discovery and addresses). */
const { t } = useI18n();
const auth = useAuthStore();
const outputs = useOutputs();
const address = ref('');
const problem = ref<'invalid_address' | 'failed' | null>(null);

async function add(): Promise<void> {
  problem.value = await addSystem(address.value.trim());
  if (problem.value === null) address.value = '';
}

async function remove(systemId: string): Promise<void> {
  problem.value = (await removeSystem(systemId)) ? null : 'failed';
}
</script>

<style scoped>
.output-state {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  white-space: nowrap;
}

.output-state[data-state='online'] {
  color: var(--color-status-ok);
}

.output-state[data-state='unreachable'] {
  color: var(--color-status-error);
}

.output-settings__form {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-3);
}

.output-settings__problem {
  margin: var(--space-2) 0 0;
  color: var(--color-status-error);
}
</style>
