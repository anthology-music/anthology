<template>
  <section class="resolved" data-testid="resolved">
    <header class="resolved__header">
      <h2 class="resolved__title">{{ resolved.item.title || t('sources.tracks') }}</h2>
      <span v-if="resolved.item.artist" class="text-muted">{{ resolved.item.artist }}</span>
      <span class="text-muted" data-testid="resolved-selected">
        {{ t('sources.selected', { n: selected.size }, selected.size) }}
      </span>
    </header>
    <ul class="resolved__tracks">
      <li
        v-for="track in resolved.tracks"
        :key="track.ref"
        class="resolved__track"
        :data-testid="`resolved-${track.ref}`"
      >
        <label class="resolved__select">
          <input
            type="checkbox"
            :checked="selected.has(track.ref)"
            :aria-label="t('sources.select', { title: track.title })"
            @change="toggle(track.ref)"
          />
          <span class="mono text-muted">{{ track.track_number ?? '' }}</span>
          <span class="resolved__main">
            <span>{{ track.title }}</span>
            <span class="text-muted">{{ track.artist }}</span>
          </span>
        </label>
        <span class="mono text-muted">{{ qualityLabel(track.offered) }}</span>
        <span
          class="resolved__status"
          :class="`resolved__status--${track.status}`"
          :data-testid="`status-${track.ref}`"
        >
          <q-icon :name="ICONS[track.status]" aria-hidden="true" />
          {{ t(`sources.duplicate.${track.status}`) }}
        </span>
      </li>
    </ul>
    <slot :selected="[...selected]" />
  </section>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { reactive } from 'vue';
import { useI18n } from 'vue-i18n';

import { qualityLabel } from '../services';

/** The tracks of a link or search result with their duplicate status (spec: sources, Search
 * and links); present tracks start unselected. */
const props = defineProps<{ resolved: Schemas['ResolveOut'] }>();

const ICONS = { present: 'library_music', better: 'upgrade', new: 'fiber_new' } as const;
const { t } = useI18n();
const selected = reactive(
  new Set(props.resolved.tracks.filter((t) => t.status !== 'present').map((t) => t.ref)),
);

function toggle(ref: string): void {
  if (selected.has(ref)) selected.delete(ref);
  else selected.add(ref);
}
</script>

<style scoped>
.resolved__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.resolved__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--weight-medium);
}

.resolved__tracks {
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
}

.resolved__track {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--touch-target);
  border-bottom: 1px solid var(--color-divider);
}

.resolved__select {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.resolved__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.resolved__status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
}

.resolved__status--present {
  color: var(--color-status-duplicate);
}

.resolved__status--better {
  color: var(--color-status-warning);
}

.resolved__status--new {
  color: var(--color-status-ok);
}
</style>
