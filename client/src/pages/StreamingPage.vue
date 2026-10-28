<template>
  <q-page class="page">
    <PageHeader
      :title="t('pages.streaming.title')"
      :description="t('pages.streaming.description')"
    />
    <SourceSearch v-if="auth.canEdit" />
    <SourceStatus v-else />
    <OrdersView v-if="auth.canEdit" />
    <ImportsView v-if="auth.isAdmin" />
    <JobsView />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';
import JobsView from '@/features/jobs/components/JobsView.vue';
import ImportsView from '@/features/library-import/components/ImportsView.vue';
import OrdersView from '@/features/sources/components/OrdersView.vue';
import SourceSearch from '@/features/sources/components/SourceSearch.vue';
import SourceStatus from '@/features/sources/components/SourceStatus.vue';
import { useAuthStore } from '@/features/users/store';

const { t } = useI18n();
const auth = useAuthStore();
</script>
