<template>
  <q-page class="page">
    <PageHeader :title="t('pages.settings.title')" :description="t('pages.settings.description')" />
    <div class="settings">
      <MyDevices />
      <UserAdministration v-if="auth.isAdmin" />
      <IdentificationSettings v-if="auth.isAdmin || auth.user?.role === 'editor'" />
      <AdoptionSettings v-if="auth.isAdmin" />
      <ServiceOverview v-if="auth.isAdmin" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';
import ServiceOverview from '@/components/ServiceOverview.vue';
import AdoptionSettings from '@/features/library/components/AdoptionSettings.vue';
import IdentificationSettings from '@/features/library/components/IdentificationSettings.vue';
import MyDevices from '@/features/users/components/MyDevices.vue';
import UserAdministration from '@/features/users/components/UserAdministration.vue';
import { useAuthStore } from '@/features/users/store';

const { t } = useI18n();
const auth = useAuthStore();
</script>
