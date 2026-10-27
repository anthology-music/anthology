<template>
  <div v-if="player.current" class="player-bar" role="region" :aria-label="t('playback.title')">
    <div class="player-bar__track" data-testid="player-track">
      <div class="player-bar__cover" aria-hidden="true"><q-icon name="music_note" /></div>
      <div class="player-bar__text">
        <span class="player-bar__title" data-testid="player-title">{{ player.current.title }}</span>
        <span class="text-muted player-bar__sub">
          {{ player.current.artist }} · {{ player.current.album }}
        </span>
        <!-- The original's effective quality, also when a transcode plays. -->
        <QualityBadge
          class="player-bar__quality"
          :effective="player.current.effective_quality"
          :status="player.current.quality_status"
        />
        <span v-if="problem" class="player-bar__problem" role="status" data-testid="player-problem">
          <q-icon name="info" aria-hidden="true" /> {{ t(`playback.problem.${problem}`) }}
        </span>
      </div>
    </div>

    <div class="player-bar__center">
      <div class="player-bar__controls">
        <q-btn
          flat
          round
          icon="skip_previous"
          :aria-label="t('playback.previous')"
          data-testid="player-previous"
          @click="player.previous()"
        />
        <q-btn
          round
          unelevated
          color="primary"
          :icon="player.playing ? 'pause' : 'play_arrow'"
          :aria-label="player.playing ? t('playback.pause') : t('playback.play')"
          data-testid="player-toggle"
          @click="player.toggle()"
        />
        <q-btn
          flat
          round
          icon="skip_next"
          :aria-label="t('playback.next')"
          data-testid="player-next"
          @click="player.next()"
        />
      </div>
      <div class="player-bar__seek">
        <span class="mono text-muted" data-testid="player-position">
          {{ formatDuration(player.positionMs) }}
        </span>
        <q-slider
          :model-value="player.positionMs"
          :min="0"
          :max="Math.max(player.durationMs, 1)"
          :step="1000"
          :aria-label="t('playback.seek')"
          class="player-bar__slider"
          data-testid="player-seek"
          @change="(value: number | null) => player.seek(value ?? 0)"
        />
        <span class="mono text-muted" data-testid="player-duration">
          {{ formatDuration(player.durationMs) }}
        </span>
      </div>
    </div>

    <div class="player-bar__end">
      <q-icon name="volume_up" aria-hidden="true" />
      <q-slider
        :model-value="player.volume"
        :min="0"
        :max="1"
        :step="0.05"
        :aria-label="t('playback.volume')"
        class="player-bar__volume"
        @update:model-value="(value: number | null) => player.setVolume(value ?? 0)"
      />
      <q-btn
        flat
        round
        icon="queue_music"
        :aria-label="t('playback.queue')"
        :aria-expanded="queueOpen"
        data-testid="player-queue"
        @click="queueOpen = !queueOpen"
      />
    </div>

    <QueuePanel
      v-if="queueOpen && player.state"
      :key="player.state.generation"
      :generation="player.state.generation"
      class="player-bar__queue"
    />
    <p v-if="player.message" class="player-bar__message" role="status" data-testid="player-message">
      {{ t(`playback.message.${player.message}`) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import QualityBadge from '@/features/library/components/QualityBadge.vue';
import { formatDuration } from '@/features/library/format';

import { usePlayerStore } from '../store';
import QueuePanel from './QueuePanel.vue';

/** The player bar of this device (spec: playback, Player controls; mockup Lokal-Hoeren). */
const { t } = useI18n();
const player = usePlayerStore();
const queueOpen = ref(false);
const problem = computed(() => (player.loaded ? player.problems.get(player.loaded) : undefined));

onMounted(() => player.start());
onBeforeUnmount(() => player.stop());
</script>

<style scoped>
.player-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface-raised);
  border-top: 1px solid var(--color-border);
}

.player-bar__track {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.player-bar__cover {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-sm);
  background: var(--color-hover);
}

.player-bar__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.player-bar__title,
.player-bar__sub {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.player-bar__title {
  font-weight: var(--weight-medium);
}

.player-bar__quality {
  align-self: flex-start;
}

.player-bar__problem {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.player-bar__center {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.player-bar__controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.player-bar__seek {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
}

.player-bar__slider {
  flex: 1;
}

.player-bar__end {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.player-bar__volume {
  width: 100px;
}

.player-bar__queue {
  grid-column: 1 / -1;
}

.player-bar__message {
  grid-column: 1 / -1;
  margin: 0;
}

@media (max-width: 839px) {
  .player-bar {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .player-bar__center {
    grid-row: 2;
    grid-column: 1 / -1;
  }

  .player-bar__volume {
    display: none;
  }
}
</style>
