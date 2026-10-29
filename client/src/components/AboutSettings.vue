<template>
  <section class="settings-section" aria-labelledby="about-title">
    <h2 id="about-title" class="settings-section__title">{{ t('about.title') }}</h2>
    <p
      v-if="about?.prerelease"
      class="about__prerelease"
      role="note"
      data-testid="about-prerelease"
    >
      <q-icon name="science" aria-hidden="true" /> {{ t('about.prerelease') }}
    </p>
    <dl class="about__facts">
      <dt>{{ t('about.server') }}</dt>
      <dd class="mono" data-testid="about-server">
        {{ about ? about.version : '…' }}
        <template v-if="about?.build_version"> · {{ about.build_version }}</template>
        <template v-if="about?.build_commit"> · {{ about.build_commit.slice(0, 12) }}</template>
      </dd>
      <dt>{{ t('about.client') }}</dt>
      <dd class="mono" data-testid="about-client">
        {{ CLIENT_VERSION }}
        <span
          v-if="about && about.version !== CLIENT_VERSION"
          class="about__mismatch"
          role="status"
        >
          · <q-icon name="warning" aria-hidden="true" /> {{ t('about.mismatch') }}
        </span>
      </dd>
      <dt>{{ t('about.license') }}</dt>
      <dd>
        <a :href="`${source}/blob/main/LICENSE`" target="_blank" rel="noopener">
          {{ about?.license ?? 'MIT' }}
        </a>
      </dd>
      <dt>{{ t('about.source') }}</dt>
      <dd>
        <a :href="source" target="_blank" rel="noopener" data-testid="about-source">{{ source }}</a>
      </dd>
    </dl>
    <q-btn
      outline
      no-caps
      icon="description"
      :label="t('about.thirdParty')"
      data-testid="about-licenses"
      @click="showLicenses"
    />
    <q-dialog v-model="open">
      <q-card class="about__licenses" data-testid="about-licenses-dialog">
        <q-card-section class="about__licenses-head">
          <h3 class="about__licenses-title">{{ t('about.thirdParty') }}</h3>
          <q-btn v-close-popup flat round icon="close" :aria-label="t('about.close')" />
        </q-card-section>
        <q-card-section>
          <p v-if="licenses === null" class="text-muted">{{ t('about.loading') }}</p>
          <pre v-else class="about__text mono">{{ licenses }}</pre>
        </q-card-section>
      </q-card>
    </q-dialog>
  </section>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';
import { CLIENT_VERSION } from '@/version';

/** Version, build and licenses of this installation (change first-release). */
const { t } = useI18n();
const about = ref<Schemas['About'] | null>(null);
const licenses = ref<string | null>(null);
const open = ref(false);
const source = computed(
  () => about.value?.source ?? 'https://github.com/anthology-music/anthology',
);

onMounted(async () => {
  const { data } = await getServices().api.GET('/api/v1/about');
  about.value = data ?? null;
});

async function showLicenses(): Promise<void> {
  open.value = true;
  if (licenses.value !== null) return;
  const { data } = await getServices().api.GET('/api/v1/about/licenses', { parseAs: 'text' });
  licenses.value = data ?? t('about.unavailable');
}
</script>

<style scoped>
.about__prerelease {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-active-bg);
}

.about__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-1) var(--space-4);
  margin: 0 0 var(--space-3);
}

.about__facts dt {
  color: var(--color-text-secondary);
}

.about__facts dd {
  margin: 0;
}

.about__mismatch {
  color: var(--color-status-warning);
}

.about__licenses {
  width: min(900px, 100vw);
}

.about__licenses-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.about__licenses-title {
  margin: 0;
  font-size: var(--text-lg);
}

.about__text {
  max-height: 70vh;
  overflow: auto;
  font-size: var(--text-xs);
  white-space: pre-wrap;
}
</style>
