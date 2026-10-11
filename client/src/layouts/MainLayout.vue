<template>
  <q-layout view="lHh LpR lFf">
    <q-drawer v-model="drawerOpen" show-if-above :width="220" :breakpoint="840" class="sidebar">
      <div class="sidebar__inner">
        <div class="sidebar__brand">
          <q-icon name="library_music" size="24px" aria-hidden="true" />
          <span>{{ t('app.name') }}</span>
        </div>

        <nav :aria-label="t('nav.main')" class="sidebar__nav">
          <router-link
            v-for="item in navigation"
            :key="item.name"
            :to="{ name: item.name }"
            class="sidebar__link"
            active-class="sidebar__link--active"
          >
            <q-icon :name="item.icon" size="20px" aria-hidden="true" />
            <span class="sidebar__label">{{ t(`nav.${item.name}`) }}</span>
          </router-link>
        </nav>

        <div class="sidebar__footer">
          <ConnectionState />
          <div class="sidebar__user">{{ t('user.signedOut') }}</div>
        </div>
      </div>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
// Drawer width matches --sidebar-width in docs/design/tokens.css.
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import ConnectionState from '@/components/ConnectionState.vue';

const { t } = useI18n();
const drawerOpen = ref(false);

const navigation = [
  { name: 'streaming', icon: 'cloud_download' },
  { name: 'local', icon: 'library_music' },
  { name: 'works', icon: 'queue_music' },
  { name: 'settings', icon: 'settings' },
] as const;
</script>

<style scoped>
.sidebar {
  background: var(--color-sidebar);
  border-right: 1px solid var(--color-border);
}

.sidebar__inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--space-5) var(--space-3);
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-3) var(--space-5);
  font-size: var(--text-lg);
  font-weight: var(--weight-bold);
  color: var(--color-accent-strong);
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar__link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  text-decoration: none;
}

.sidebar__link:hover {
  background: var(--color-hover);
}

.sidebar__link--active {
  background: var(--color-hover);
  color: var(--color-text);
  font-weight: var(--weight-medium);
}

.sidebar__footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
}

.sidebar__user {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}
</style>
