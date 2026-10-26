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

/** The number of open entries of a list in the navigation (counts only, no rows). */
const props = withDefaults(defineProps<{ stream?: string }>(), { stream: 'review.items' });
const { t } = useI18n();
const { number } = useCounts();
const subscription = useSubscription(props.stream, { status: 'open' }, [0, 0]);
</script>

<style scoped>
.review-count {
  margin-left: auto;
}
</style>
