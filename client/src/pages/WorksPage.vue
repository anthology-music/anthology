<template>
  <q-page class="page">
    <PageHeader :title="t('pages.works.title')" :description="t('pages.works.description')" />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';

const { t } = useI18n();
</script>
