<template>
  <q-page class="page">
    <PageHeader
      :title="t('pages.streaming.title')"
      :description="t('pages.streaming.description')"
    />
    <JobsView />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';
import JobsView from '@/features/jobs/components/JobsView.vue';

const { t } = useI18n();
</script>
