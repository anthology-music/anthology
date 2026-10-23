<template>
  <span
    v-if="subscription.total"
    class="badge review-count"
    data-testid="review-nav-count"
    :aria-label="t('review.openCount', { n: number(subscription.total) }, subscription.total)"
  >
    {{ number(subscription.total) }}
  </span>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import { useCounts } from '@/features/library/numbers';
import { useSubscription } from '@/sync/useSubscription';

/** The number of open review entries in the navigation (counts only, no rows). */
const { t } = useI18n();
const { number } = useCounts();
const subscription = useSubscription('review.items', { status: 'open' }, [0, 0]);
</script>

<style scoped>
.review-count {
  margin-left: auto;
}
</style>
