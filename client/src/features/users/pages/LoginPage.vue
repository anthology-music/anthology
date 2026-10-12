<template>
  <q-form class="auth-form" @submit.prevent="submit">
    <h1 class="auth-form__title">{{ t('auth.login.title') }}</h1>
    <q-input
      v-model="username"
      :label="t('auth.username')"
      autocomplete="username"
      autofocus
      outlined
      :rules="[required]"
    />
    <q-input
      v-model="password"
      :label="t('auth.password')"
      type="password"
      autocomplete="current-password"
      outlined
      :rules="[required]"
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
      :label="t('auth.login.submit')"
    />
  </q-form>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

import { AuthError } from '../session';
import { useAuthStore } from '../store';

const { t } = useI18n();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const username = ref('');
const password = ref('');
const busy = ref(false);
const error = ref<string | null>(null);

const required = (value: string) => value.trim() !== '' || t('auth.errors.required');

async function submit() {
  busy.value = true;
  error.value = null;
  try {
    await auth.login(username.value.trim(), password.value);
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await router.replace(redirect.startsWith('/') ? redirect : '/');
  } catch (caught) {
    error.value = caught instanceof AuthError ? caught.code : 'failed';
  } finally {
    busy.value = false;
  }
}
</script>
