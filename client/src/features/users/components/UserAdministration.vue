<template>
  <section class="settings-section" aria-labelledby="users-title">
    <h2 id="users-title" class="settings-section__title">
      {{ t('users.title') }}
      <span v-if="subscription.total !== null" class="mono text-muted">
        {{ subscription.total }}
      </span>
    </h2>

    <ul class="item-list">
      <li v-for="user in users" :key="user.id" class="item-list__row">
        <q-icon name="person" size="20px" aria-hidden="true" />
        <div class="item-list__main">
          <span>{{ user.display_name }}</span>
          <span class="mono text-muted item-list__sub">{{ user.username }}</span>
        </div>
        <q-select
          :model-value="user.role"
          :options="roleOptions"
          emit-value
          map-options
          dense
          outlined
          :aria-label="t('users.roleOf', { name: user.display_name })"
          @update:model-value="(role: string) => update(user.id, { role })"
        />
        <q-toggle
          :model-value="user.active"
          :label="user.active ? t('users.active') : t('users.inactive')"
          @update:model-value="(active: boolean) => update(user.id, { active })"
        />
      </li>
    </ul>
    <p v-if="error" class="form-error" role="alert">
      <q-icon name="error_outline" aria-hidden="true" />{{ t(`users.errors.${error}`) }}
    </p>

    <q-form class="create-user" @submit.prevent="create">
      <h3 class="create-user__title">{{ t('users.create') }}</h3>
      <q-input v-model="form.display_name" :label="t('auth.displayName')" dense outlined />
      <q-input v-model="form.username" :label="t('auth.username')" dense outlined />
      <q-input
        v-model="form.password"
        :label="t('auth.password')"
        type="password"
        autocomplete="new-password"
        dense
        outlined
      />
      <q-select
        v-model="form.role"
        :options="roleOptions"
        :label="t('users.role')"
        emit-value
        map-options
        dense
        outlined
      />
      <q-btn
        type="submit"
        color="primary"
        text-color="dark"
        unelevated
        no-caps
        :label="t('users.createSubmit')"
      />
    </q-form>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';
import { useSubscription } from '@/sync/useSubscription';

interface UserRow {
  id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'editor' | 'listener';
  active: boolean;
}

const { t } = useI18n();
const subscription = useSubscription('users', {}, [0, 200]);
const error = ref<string | null>(null);
const form = reactive({ display_name: '', username: '', password: '', role: 'listener' as const });

const roleOptions = computed(() =>
  (['admin', 'editor', 'listener'] as const).map((role) => ({
    value: role,
    label: t(`roles.${role}`),
  })),
);

const users = computed(
  () =>
    [...subscription.value.rows.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, row]) => row) as unknown as UserRow[],
);

function errorCode(detail: unknown): string {
  const code = (detail as { detail?: unknown } | undefined)?.detail;
  return code === 'last_admin' || code === 'conflict' ? code : 'failed';
}

async function update(userId: string, changes: { role?: string; active?: boolean }) {
  error.value = null;
  const { error: failed } = await getServices().api.PATCH('/api/v1/users/{user_id}', {
    params: { path: { user_id: userId } },
    body: changes as { role?: UserRow['role']; active?: boolean },
  });
  if (failed) error.value = errorCode(failed);
}

async function create() {
  error.value = null;
  const { error: failed } = await getServices().api.POST('/api/v1/users', {
    body: { ...form, username: form.username.trim(), display_name: form.display_name.trim() },
  });
  if (failed) {
    error.value = errorCode(failed);
    return;
  }
  Object.assign(form, { display_name: '', username: '', password: '', role: 'listener' });
}
</script>
