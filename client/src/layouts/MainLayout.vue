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
          <ConnectionState :state="sync.connection" />
          <q-btn
            v-if="auth.user"
            flat
            no-caps
            align="left"
            class="sidebar__user"
            :aria-label="t('userMenu')"
          >
            <div class="sidebar__user-text">
              <span>{{ auth.user.display_name }}</span>
              <span class="text-muted">{{ t(`roles.${auth.user.role}`) }}</span>
            </div>
            <q-menu anchor="top left" self="bottom left">
              <q-list>
                <q-item v-close-popup clickable @click="logout">
                  <q-item-section avatar><q-icon name="logout" /></q-item-section>
                  <q-item-section>{{ t('auth.logout') }}</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </q-btn>
          <div v-else class="sidebar__user">{{ t('user.signedOut') }}</div>
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
import { useRouter } from 'vue-router';

import ConnectionState from '@/components/ConnectionState.vue';
import { useAuthStore } from '@/features/users/store';
import { useSyncStore } from '@/sync/store';

const { t } = useI18n();
const auth = useAuthStore();
const sync = useSyncStore();
const router = useRouter();

async function logout() {
  await auth.logout();
  await router.replace({ name: 'login' });
}
const drawerOpen = ref(false);

const navigation = [
  { name: 'streaming', icon: 'cloud_download' },
  { name: 'local', icon: 'library_music' },
  { name: 'works', icon: 'queue_music' },
  { name: 'settings', icon: 'settings' },
  ...(import.meta.env.DEV ? [{ name: 'demo', icon: 'science' } as const] : []),
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

.sidebar__user-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.3;
}
</style>
