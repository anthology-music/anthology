<template>
  <q-btn
    flat
    round
    :size="size"
    :icon="on ? 'favorite' : 'favorite_border'"
    :color="on ? 'primary' : undefined"
    :aria-label="
      on ? t('personal.favorites.remove', { name }) : t('personal.favorites.add', { name })
    "
    :aria-pressed="on"
    :data-testid="`favorite-${type}-${id}`"
    @click.stop.prevent="favorites.toggle(type, id)"
  />
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';

import type { FavoriteTarget } from '../api';
import { useFavoritesStore } from '../favorites';

/** Mark a recording, album or artist as a favorite of this user. */
const props = withDefaults(
  defineProps<{ type: FavoriteTarget; id: string; name: string; size?: string }>(),
  { size: 'md' },
);

const { t } = useI18n();
const favorites = useFavoritesStore();
const on = computed(() => favorites.has(props.type, props.id));

onMounted(() => favorites.start());
</script>
