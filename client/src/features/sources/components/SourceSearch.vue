<template>
  <section class="source-search" :aria-label="t('sources.title')">
    <form class="source-search__form" @submit.prevent="submit">
      <q-input
        v-model="text"
        class="source-search__query"
        outlined
        dense
        :label="t('sources.query')"
        :placeholder="t('sources.placeholder')"
        data-testid="source-query"
      />
      <q-select
        v-model="quality"
        class="source-search__quality"
        outlined
        dense
        emit-value
        map-options
        :options="qualityOptions"
        :label="t('sources.quality')"
        data-testid="source-quality"
      />
      <fieldset class="source-search__mode">
        <legend class="text-muted">{{ t('sources.mode.label') }}</legend>
        <label
          ><input type="radio" name="source-mode" checked /> {{ t('sources.mode.audio') }}</label
        >
        <label :title="t('sources.mode.videoLater')" class="text-muted">
          <input type="radio" name="source-mode" disabled /> {{ t('sources.mode.video') }}
        </label>
      </fieldset>
      <q-btn
        type="submit"
        unelevated
        no-caps
        color="primary"
        :label="isLink(text) ? t('sources.open') : t('sources.search')"
        :loading="busy"
        :disable="!text.trim() || !available.length"
        data-testid="source-submit"
      />
    </form>
    <div class="source-search__sources" role="group" :aria-label="t('sources.source')">
      <span class="text-muted">{{ t('sources.source') }}</span>
      <q-btn
        flat
        no-caps
        :label="t('sources.all')"
        :aria-pressed="service === null"
        :class="{ 'source-search__chip--active': service === null }"
        data-testid="source-all"
        @click="service = null"
      />
      <q-btn
        v-for="item in available"
        :key="item.id"
        flat
        no-caps
        :aria-pressed="service === item.id"
        :class="{ 'source-search__chip--active': service === item.id }"
        :data-testid="`source-${item.id}`"
        @click="service = item.id"
      >
        <span class="mono source-search__short">{{ item.short }}</span
        >{{ item.name }}
      </q-btn>
      <SourceStatus :services="all" />
    </div>
    <p v-if="!available.length" class="text-muted" data-testid="source-none">
      {{ t('sources.none') }}
    </p>
    <p v-if="error" role="alert" class="form-error" data-testid="source-error">
      {{ t(`sources.errors.${error}`) }}
    </p>

    <ResolvedTracks v-if="resolved" :key="resolvedKey" :resolved="resolved">
      <template #default="{ selected }">
        <slot name="order" :resolved="resolved" :selected="selected" :quality="quality" />
      </template>
    </ResolvedTracks>
    <div v-else-if="results.length" class="source-search__results" data-testid="source-results">
      <section v-for="group in results" :key="group.service">
        <h2 class="source-search__group">
          {{ serviceName(group.service) }}
          <span v-if="group.error" class="text-muted">
            · {{ t(`sources.errors.${group.error === 'timeout' ? 'timeout' : 'failed'}`) }}
          </span>
        </h2>
        <p v-if="!group.results.length && !group.error" class="text-muted">
          {{ t('sources.noResults') }}
        </p>
        <ul class="source-search__list">
          <li
            v-for="result in group.results"
            :key="result.ref"
            class="source-search__result"
            :data-testid="`result-${result.ref}`"
          >
            <q-icon :name="KIND_ICONS[result.kind] ?? 'music_note'" aria-hidden="true" />
            <span class="source-search__main">
              <span>{{ result.title }}</span>
              <span class="text-muted">
                {{ [result.artist, result.album, result.year].filter(Boolean).join(' · ') }}
              </span>
            </span>
            <span class="mono text-muted">{{ qualityLabel(result.offered) }}</span>
            <q-btn
              flat
              no-caps
              :label="t('sources.showTracks')"
              :data-testid="`open-${result.ref}`"
              @click="open(group.service, result.ref)"
            />
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { getServices } from '@/services';

import { isLink, qualityLabel, useSourceServices } from '../services';
import ResolvedTracks from './ResolvedTracks.vue';
import SourceStatus from './SourceStatus.vue';

/** Search the sources or open a link (spec: sources, Search and links; mockup Main). */
const KIND_ICONS: Record<string, string> = {
  album: 'album',
  track: 'music_note',
  playlist: 'queue_music',
};

const { t } = useI18n();
const { all, available } = useSourceServices();
const text = ref('');
const service = ref<string | null>(null);
const quality = ref('best');
const busy = ref(false);
const error = ref<string | null>(null);
const results = ref<Schemas['ServiceResults'][]>([]);
const resolved = ref<Schemas['ResolveOut'] | null>(null);
const resolvedKey = ref(0);

const qualityOptions = computed(() => {
  const chosen = available.value.filter((s) => service.value === null || s.id === service.value);
  const values = [...new Set(chosen.flatMap((s) => s.qualities))];
  return (values.length ? values : ['best']).map((value) => ({
    value,
    label: t(`sources.qualities.${value}`, value),
  }));
});

const serviceName = (id: string) => all.value.find((s) => s.id === id)?.name ?? id;

async function submit(): Promise<void> {
  error.value = null;
  if (isLink(text.value)) {
    await resolve({ url: text.value.trim() });
    return;
  }
  busy.value = true;
  resolved.value = null;
  const { data, error: failed } = await getServices().api.POST('/api/v1/sources/search', {
    body: {
      query: text.value.trim(),
      service: service.value,
      kinds: ['album', 'track', 'playlist'],
      page: 1,
      page_size: 20,
    },
  });
  busy.value = false;
  if (failed || !data) {
    error.value = 'failed';
    return;
  }
  results.value = data;
}

async function open(serviceId: string, ref_: string): Promise<void> {
  await resolve({ service: serviceId, ref: ref_ });
}

async function resolve(body: Schemas['ResolveIn']): Promise<void> {
  busy.value = true;
  error.value = null;
  const {
    data,
    error: failed,
    response,
  } = await getServices().api.POST('/api/v1/sources/resolve', { body });
  busy.value = false;
  if (failed || !data) {
    error.value = response.status === 422 ? 'noSourceForLink' : 'failed';
    return;
  }
  resolved.value = data;
  resolvedKey.value += 1;
}

defineExpose({ clear: () => (resolved.value = null) });
</script>

<style scoped>
.source-search__form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3);
}

.source-search__query {
  flex: 1 1 320px;
}

.source-search__quality {
  flex: 0 1 200px;
}

.source-search__mode {
  display: flex;
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  border: 0;
}

.source-search__mode label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: var(--touch-target);
}

.source-search__sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-3) 0;
}

.source-search__chip--active {
  background: var(--color-active-bg);
}

.source-search__short {
  margin-right: var(--space-1);
}

.source-search__group {
  margin: var(--space-3) 0 var(--space-2);
  font-size: var(--text-base);
  font-weight: var(--weight-medium);
}

.source-search__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-search__result {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target);
  border-bottom: 1px solid var(--color-divider);
}

.source-search__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
</style>
