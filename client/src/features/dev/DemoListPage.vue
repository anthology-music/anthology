<template>
  <q-page class="page demo-page">
    <PageHeader :title="t('demo.title')" :description="t('demo.description')" />
    <p v-if="subscription.error" class="form-error" role="alert">
      <q-icon name="info" aria-hidden="true" />{{ t('demo.unavailable') }}
    </p>
    <template v-else>
      <p class="demo-page__count">
        <span class="mono" data-testid="demo-total">{{ formattedTotal }}</span>
        {{ t('demo.rows') }}
        <span v-if="subscription.source === 'cache'" class="badge">{{ t('demo.cached') }}</span>
      </p>
      <div class="demo-page__list">
        <VirtualList :subscription="subscription" :label="t('demo.title')">
          <template #default="{ row, position }">
            <span class="mono text-muted demo-page__position">{{ position + 1 }}</span>
            <div class="item-list__main">
              <span>{{ row.title }}</span>
              <span class="text-muted item-list__sub">{{ row.artist }}</span>
            </div>
            <span class="mono text-muted">{{ row.year }}</span>
          </template>
        </VirtualList>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import PageHeader from '@/components/PageHeader.vue';
import VirtualList from '@/components/VirtualList.vue';
import { useSubscription } from '@/sync/useSubscription';

const { t, locale } = useI18n();
const subscription = useSubscription('demo.items', {}, [0, 100]);

const formattedTotal = computed(() =>
  subscription.value.total === null
    ? '…'
    : new Intl.NumberFormat(locale.value).format(subscription.value.total),
);
</script>

<style scoped>
.demo-page {
  display: flex;
  flex-direction: column;
}

.demo-page__count {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
}

/* The list needs a bounded height (it scrolls inside); flex growth would follow the content. */
.demo-page__list {
  height: calc(100vh - 220px);
  min-height: 300px;
}

.demo-page__position {
  min-width: 7ch;
  text-align: right;
  margin-right: var(--space-3);
}
</style>
