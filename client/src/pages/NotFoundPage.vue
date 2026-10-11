<template>
  <q-page class="page column items-center justify-center">
    <PageHeader :title="t('pages.notFound.title')" />
    <router-link :to="{ name: 'local' }">{{ t('pages.notFound.back') }}</router-link>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';

const { t } = useI18n();
</script>
