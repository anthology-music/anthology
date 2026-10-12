<template>
  <q-form class="auth-form" @submit.prevent="submit">
    <h1 class="auth-form__title">{{ t('auth.setup.title') }}</h1>
    <p class="auth-form__hint">{{ t('auth.setup.hint') }}</p>
    <q-input
      v-model="displayName"
      :label="t('auth.displayName')"
      autocomplete="name"
      autofocus
      outlined
      :rules="[required]"
    />
    <q-input
      v-model="username"
      :label="t('auth.username')"
      autocomplete="username"
      outlined
      :rules="[required, validUsername]"
    />
    <q-input
      v-model="password"
      :label="t('auth.password')"
      type="password"
      autocomplete="new-password"
      outlined
      :hint="t('auth.passwordHint')"
      :rules="[longEnough]"
    />
    <p v-if="error" class="auth-form__error" role="alert">
      <q-icon name="error_outline" aria-hidden="true" />
      {{ t(`auth.errors.${error}`) }}
    </p>
    <q-btn
      type="submit"
      color="primary"
      text-color="dark"
      unelevated
      no-caps
      :loading="busy"
      :label="t('auth.setup.submit')"
    />
  </q-form>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { AuthError } from '../session';
import { useAuthStore } from '../store';

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();

const displayName = ref('');
const username = ref('');
const password = ref('');
const busy = ref(false);
const error = ref<string | null>(null);

const required = (value: string) => value.trim() !== '' || t('auth.errors.required');
const validUsername = (value: string) =>
  /^[A-Za-z0-9._-]{1,64}$/.test(value.trim()) || t('auth.errors.username');
const longEnough = (value: string) => value.length >= 8 || t('auth.passwordHint');

async function submit() {
  busy.value = true;
  error.value = null;
  try {
    await auth.setup({
      username: username.value.trim(),
      display_name: displayName.value.trim(),
      password: password.value,
    });
    await router.replace({ name: 'local' });
  } catch (caught) {
    error.value = caught instanceof AuthError ? caught.code : 'failed';
  } finally {
    busy.value = false;
  }
}
</script>
