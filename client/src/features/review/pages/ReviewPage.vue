<template>
  <q-page class="page">
    <PageHeader :title="t('review.title')" :description="t('review.description')" />
    <ReviewView :key="key" :filter="filter" @update:filter="filter = $event" />
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';

import ReviewView from '../components/ReviewView.vue';
import { DEFAULT_FILTER, type ReviewFilter } from '../review';

/** The review list (spec: review); only for editors and admins. */
const { t } = useI18n();
const filter = ref<ReviewFilter>({ ...DEFAULT_FILTER });
// Subscription parameters are fixed: a new filter mounts a new list.
const key = computed(() => JSON.stringify(filter.value));
</script>
