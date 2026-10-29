<template>
  <q-page class="page">
    <PageHeader :title="t('pages.settings.title')" :description="t('pages.settings.description')" />
    <div class="settings">
      <MyDevices />
      <PlaybackSettings />
      <OutputSettings />
      <UserAdministration v-if="auth.isAdmin" />
      <SourceSettings v-if="auth.isAdmin" />
      <IdentificationSettings v-if="auth.isAdmin || auth.user?.role === 'editor'" />
      <QualitySettings v-if="auth.isAdmin || auth.user?.role === 'editor'" />
      <ChangeHistory v-if="auth.canEdit" />
      <AdoptionSettings v-if="auth.isAdmin" />
      <SupersededSettings v-if="auth.isAdmin" />
      <MaintenanceSettings v-if="auth.isAdmin" />
      <ServiceOverview v-if="auth.isAdmin" />
      <AboutSettings />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import AboutSettings from '@/components/AboutSettings.vue';
import PageHeader from '@/components/PageHeader.vue';
import ServiceOverview from '@/components/ServiceOverview.vue';
import AdoptionSettings from '@/features/library/components/AdoptionSettings.vue';
import SupersededSettings from '@/features/library/components/SupersededSettings.vue';
import IdentificationSettings from '@/features/library/components/IdentificationSettings.vue';
import MaintenanceSettings from '@/features/library/components/MaintenanceSettings.vue';
import OutputSettings from '@/features/playback/components/OutputSettings.vue';
import PlaybackSettings from '@/features/playback/components/PlaybackSettings.vue';
import QualitySettings from '@/features/quality-analysis/components/QualitySettings.vue';
import SourceSettings from '@/features/sources/components/SourceSettings.vue';
import ChangeHistory from '@/features/tagging/components/ChangeHistory.vue';
import MyDevices from '@/features/users/components/MyDevices.vue';
import UserAdministration from '@/features/users/components/UserAdministration.vue';
import { useAuthStore } from '@/features/users/store';

const { t } = useI18n();
const auth = useAuthStore();
</script>
