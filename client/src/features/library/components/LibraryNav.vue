<template>
  <nav class="library-nav" :aria-label="t('library.title')">
    <SearchField class="library-nav__search" />
    <h2 class="library-nav__title">{{ t('library.title') }}</h2>
    <router-link
      v-for="section in sections"
      :key="section.name"
      :to="{ name: section.name }"
      class="library-nav__link"
      active-class="library-nav__link--active"
      :data-testid="`library-nav-${section.counter}`"
    >
      <span>{{ t(`library.sections.${section.counter}`) }}</span>
      <span class="mono text-muted library-nav__count">
        {{ number(subscription.total === null ? null : subscription.counters[section.counter]) }}
      </span>
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import SearchField from '@/features/search/components/SearchField.vue';
import { useSubscription } from '@/sync/useSubscription';

import { useCounts } from '../numbers';

const { t } = useI18n();
const { number } = useCounts();
// An empty window: only the library counters (all top-level lists carry them), no rows.
const subscription = useSubscription('library.artists', {}, [0, 0]);

const sections = [
  { name: 'library-albums', counter: 'releases' },
  { name: 'library-artists', counter: 'artists' },
  { name: 'library-tracks', counter: 'tracks' },
] as const;
</script>

<style scoped>
.library-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.library-nav__title {
  margin: 0 0 var(--space-2);
  padding: 0 var(--space-3);
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.library-nav__link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  text-decoration: none;
}

.library-nav__link:hover {
  background: var(--color-hover);
}

.library-nav__link--active {
  background: var(--color-hover);
  color: var(--color-text);
  font-weight: var(--weight-medium);
}

/* Narrow screens: the sections become tabs above the content. */
@media (max-width: 839px) {
  .library-nav {
    flex-direction: row;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--color-border);
  }

  .library-nav__search {
    flex: 1 0 100%;
  }

  .library-nav__title {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }

  .library-nav__link {
    flex: 1 0 auto;
    justify-content: center;
    border-radius: 0;
  }

  .library-nav__link--active {
    background: none;
    box-shadow: inset 0 -2px 0 var(--color-accent);
  }
}
</style>
