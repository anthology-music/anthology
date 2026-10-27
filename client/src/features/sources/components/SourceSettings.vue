<template>
  <section class="settings-section" aria-labelledby="source-settings-title">
    <h2 id="source-settings-title" class="settings-section__title">
      {{ t('sources.settings.title') }}
    </h2>
    <p class="text-muted">{{ t('sources.settings.hint') }}</p>
    <p v-if="!all.length" class="text-muted">{{ t('sources.status.none') }}</p>
    <article
      v-for="service in all"
      :key="service.id"
      class="source-settings__service"
      :data-testid="`source-settings-${service.id}`"
    >
      <header class="source-settings__header">
        <span class="source-settings__name">{{ service.name }}</span>
        <span v-if="service.version" class="mono text-muted">{{ service.version }}</span>
        <span>
          {{
            service.available
              ? t('sources.status.available')
              : t(`sources.problems.${service.problem ?? 'unreachable'}`)
          }}
        </span>
        <span v-if="service.login_required" class="text-muted">
          {{ service.logged_in ? t('sources.settings.loggedIn') : t('sources.settings.loggedOut') }}
        </span>
      </header>
      <form
        v-if="service.login_required && logins[service.id]"
        class="source-settings__login"
        @submit.prevent="save(service.id)"
      >
        <template v-for="field in logins[service.id]!.fields" :key="field.name">
          <!-- Stored values are never shown: a fixed mask says that nothing is missing. -->
          <q-input
            v-if="!editing[service.id] && isStored(service.id, field.name)"
            :model-value="MASK"
            dense
            outlined
            readonly
            type="password"
            :label="field.label"
            :hint="t('sources.settings.storedField')"
            :data-testid="`login-${service.id}-${field.name}`"
          />
          <q-input
            v-else
            v-model="values[service.id]![field.name]"
            dense
            outlined
            autocomplete="off"
            :type="field.secret ? 'password' : 'text'"
            :label="field.label"
            :placeholder="
              isStored(service.id, field.name) ? t('sources.settings.keepPlaceholder') : ''
            "
            :data-testid="`login-${service.id}-${field.name}`"
          />
        </template>
        <q-btn
          v-if="editing[service.id] || !complete(service.id)"
          type="submit"
          unelevated
          no-caps
          color="primary"
          :label="t('sources.settings.save')"
          :data-testid="`login-save-${service.id}`"
        />
        <q-btn
          v-else
          flat
          no-caps
          :label="t('sources.settings.change')"
          :data-testid="`login-change-${service.id}`"
          @click="editing[service.id] = true"
        />
      </form>
      <p v-if="messages[service.id]" role="status" :data-testid="`login-message-${service.id}`">
        {{ t(`sources.settings.${messages[service.id]}`) }}
      </p>
    </article>
  </section>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { reactive, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';

import { useSourceServices } from '../services';

/** Source services for admins with the login form (spec: sources, Source service login). */
const { t } = useI18n();
const { all } = useSourceServices();
const logins = reactive<Record<string, Schemas['LoginOut']>>({});
const values = reactive<Record<string, Record<string, string>>>({});
const messages = reactive<Record<string, 'saved' | 'failed'>>({});
const editing = reactive<Record<string, boolean>>({});
const MASK = '••••••••';

const isStored = (id: string, name: string) => logins[id]?.stored_fields.includes(name) ?? false;
const complete = (id: string) =>
  logins[id]?.fields.every((field) => isStored(id, field.name)) ?? false;

// The login of every service that needs one, so stored fields show masked at once.
watch(
  () => all.value.filter((service) => service.login_required).map((service) => service.id),
  (ids) => {
    for (const id of ids) if (!(id in logins)) void load(id);
  },
  { immediate: true },
);

const params = (id: string) => ({ params: { path: { service_id: id } } });

async function load(id: string): Promise<void> {
  const { data } = await getServices().api.GET(
    '/api/v1/sources/services/{service_id}/login',
    params(id),
  );
  if (!data) return;
  values[id] = Object.fromEntries(data.fields.map((field) => [field.name, '']));
  logins[id] = data;
}

async function save(id: string): Promise<void> {
  const { data } = await getServices().api.PUT('/api/v1/sources/services/{service_id}/login', {
    ...params(id),
    body: { fields: { ...values[id] } },
  });
  // The values are not kept in the page once they are stored.
  values[id] = Object.fromEntries(Object.keys(values[id] ?? {}).map((name) => [name, '']));
  if (data) logins[id] = data;
  editing[id] = false;
  messages[id] = data?.logged_in ? 'saved' : 'failed';
}
</script>

<style scoped>
.source-settings__service {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-divider);
}

.source-settings__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-3);
}

.source-settings__name {
  font-weight: var(--weight-medium);
}

.source-settings__login {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
</style>
