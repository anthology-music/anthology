<template>
  <q-page class="page">
    <PageHeader :title="t('pages.local.title')" :description="t('pages.local.description')" />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';

const { t } = useI18n();
</script>
