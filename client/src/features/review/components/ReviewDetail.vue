<template>
  <section class="review-detail" :aria-label="t('review.detail')" data-testid="review-detail">
    <header class="review-detail__header">
      <span class="badge">{{ t(`review.types.${item.type}`) }}</span>
      <span class="review-detail__meta text-muted">
        {{ t(`review.origins.${item.origin}`) }} ·
        {{ t(`review.confidences.${item.confidence}`) }}
      </span>
    </header>
    <h2 class="review-detail__title">{{ item.summary.subject }}</h2>

    <dl class="review-detail__compare">
      <div>
        <dt class="text-muted">{{ t(`review.current.${item.type}`) }}</dt>
        <dd :class="{ mono: monoValues }">{{ item.summary.current ?? '–' }}</dd>
      </div>
      <div>
        <dt class="text-muted">{{ t(`review.proposed.${item.type}`) }}</dt>
        <dd :class="{ mono: monoValues }" data-testid="review-proposed">
          {{ proposedText }}
        </dd>
      </div>
    </dl>

    <template v-if="match">
      <table class="review-detail__sides" data-testid="review-sides">
        <thead>
          <tr>
            <th />
            <th>{{ t('review.evidence.thisRecording') }}</th>
            <th>{{ t('review.evidence.otherRecording') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="field in SIDE_FIELDS" :key="field">
            <th class="text-muted">{{ t(`review.evidence.${field}`) }}</th>
            <td>{{ sideValue(match.subject, field) }}</td>
            <td>{{ sideValue(match.other, field) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="review-detail__note" data-testid="review-similarity">
        {{
          match.fingerprint_similarity === null || match.fingerprint_similarity === undefined
            ? t('review.evidence.notCompared')
            : t('review.evidence.similarity', { percent: percent(match.fingerprint_similarity) })
        }}
      </p>
    </template>

    <dl v-else-if="suggestion" class="review-detail__facts">
      <dt>{{ t('review.evidence.musicbrainz') }}</dt>
      <dd>{{ suggestion.artist }} – {{ suggestion.title }}</dd>
      <dt>{{ t('review.evidence.duration') }}</dt>
      <dd class="mono">
        {{ duration(suggestion.recording.duration_ms) }} /
        {{ suggestion.duration_ms ? duration(suggestion.duration_ms) : '–' }}
      </dd>
      <dt>{{ t('review.evidence.candidates') }}</dt>
      <dd>{{ suggestion.candidates }}</dd>
    </dl>

    <dl v-else-if="title" class="review-detail__facts">
      <dt>{{ t('review.evidence.path') }}</dt>
      <dd class="mono">{{ title.path }}</dd>
      <dt>{{ t('review.evidence.duration') }}</dt>
      <dd class="mono">
        {{ duration(title.recording.duration_ms) }} /
        {{ title.duration_ms ? duration(title.duration_ms) : '–' }}
      </dd>
    </dl>

    <template v-else-if="replacement">
      <dl class="review-detail__facts">
        <dt>{{ t('review.evidence.format') }}</dt>
        <dd class="mono">
          {{ replacement.recording.format?.toUpperCase() ?? '–' }} →
          {{ replacement.format?.toUpperCase() ?? '–' }}
        </dd>
      </dl>
      <div class="review-detail__spectrograms">
        <SpectrogramImage :audio-hash="replacement.current_audio_hash" />
      </div>
    </template>

    <template v-else-if="quality">
      <dl class="review-detail__facts">
        <dt>{{ t('review.evidence.finding') }}</dt>
        <dd>{{ t(`review.findings.${quality.finding}`, quality.finding) }}</dd>
        <template v-if="quality.values.cutoff_hz">
          <dt>{{ t('review.evidence.cutoff') }}</dt>
          <dd class="mono">{{ khz(Number(quality.values.cutoff_hz)) }}</dd>
        </template>
        <dt>{{ t('review.evidence.declared') }}</dt>
        <dd>{{ t(`library.quality.tiers.${quality.declared_quality}`) }}</dd>
        <dt>{{ t('review.evidence.files') }}</dt>
        <dd>{{ quality.files }}</dd>
      </dl>
      <SpectrogramImage :audio-hash="quality.audio_hash" />
    </template>

    <p v-if="!item.applicable" class="form-error" data-testid="review-unavailable">
      <q-icon name="block" aria-hidden="true" />{{ t('review.unavailable') }}
    </p>

    <p v-if="decided" class="text-muted" data-testid="review-decided">
      {{
        t('review.decidedBy', {
          name: item.decided_by_name ?? t('review.system'),
          date: date(item.decided_at),
        })
      }}
      <template v-if="item.note"> · {{ t(`review.notes.${item.note}`, item.note) }}</template>
    </p>

    <div class="review-detail__actions">
      <template v-if="item.status === 'open' || item.status === 'deferred'">
        <template v-if="item.choices.length">
          <q-btn
            v-for="choice in item.choices"
            :key="choice"
            unelevated
            no-caps
            color="primary"
            :disable="busy || !item.applicable"
            :label="t(`review.choices.${choice}`)"
            :data-testid="`review-choice-${choice}`"
            @click="emit('decide', 'accept', choice)"
          />
        </template>
        <q-btn
          v-else
          unelevated
          no-caps
          color="primary"
          :disable="busy || !item.applicable"
          :label="t(`review.accept.${item.type}`)"
          data-testid="review-accept"
          @click="emit('decide', 'accept', null)"
        />
        <q-btn
          v-if="!item.choices.length"
          outline
          no-caps
          :disable="busy"
          :label="t(`review.reject.${item.type}`)"
          data-testid="review-reject"
          @click="emit('decide', 'reject', null)"
        />
        <q-btn
          v-if="item.status === 'open'"
          flat
          no-caps
          :disable="busy"
          :label="t('review.defer')"
          data-testid="review-defer"
          @click="emit('decide', 'defer', null)"
        />
        <q-btn
          v-else
          flat
          no-caps
          :disable="busy"
          :label="t('review.reopen')"
          data-testid="review-reopen"
          @click="emit('decide', 'reopen', null)"
        />
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  ImportReplacementEvidence,
  ImportTitleEvidence,
  MusicBrainzSuggestionEvidence,
  QualityFindingEvidence,
  QualityFindingProposal,
  RecordingMatchEvidence,
  RecordingSide,
  ReviewItemRow,
} from '@anthology/api-types';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { formatDuration } from '@/features/library/format';

import type { Decision } from '../review';
import SpectrogramImage from './SpectrogramImage.vue';

const props = defineProps<{ item: ReviewItemRow; busy: boolean }>();
const emit = defineEmits<{ decide: [decision: Decision, choice: string | null] }>();

const { t, locale } = useI18n();

const SIDE_FIELDS = ['title', 'artist', 'duration', 'format', 'quality'] as const;
type SideField = (typeof SIDE_FIELDS)[number];

const evidence = computed(() => props.item.evidence as unknown);
const match = computed(() =>
  props.item.type === 'recording_match' ? (evidence.value as RecordingMatchEvidence) : null,
);
const suggestion = computed(() =>
  props.item.type === 'musicbrainz_suggestion'
    ? (evidence.value as MusicBrainzSuggestionEvidence)
    : null,
);
const title = computed(() =>
  props.item.type === 'import_title' ? (evidence.value as ImportTitleEvidence) : null,
);
const replacement = computed(() =>
  props.item.type === 'import_replacement' ? (evidence.value as ImportReplacementEvidence) : null,
);
const quality = computed(() =>
  props.item.type === 'quality_finding' ? (evidence.value as QualityFindingEvidence) : null,
);
const monoValues = computed(() => props.item.type === 'import_replacement');
const decided = computed(() => props.item.status !== 'open' && props.item.decided_at !== null);

const proposedText = computed(() => {
  if (props.item.type === 'quality_finding') {
    const tier = (props.item.proposal as unknown as QualityFindingProposal).upscaled_quality;
    return tier ? t(`library.quality.tiers.${tier}`) : '–';
  }
  return props.item.summary.proposed ?? '–';
});

const duration = (ms: number) => formatDuration(ms);
const percent = (value: number) =>
  new Intl.NumberFormat(locale.value, { style: 'percent' }).format(value);
const khz = (hz: number) =>
  new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 }).format(hz / 1000) + ' kHz';
const date = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(value),
      )
    : '';

function sideValue(side: RecordingSide, field: SideField): string {
  if (field === 'duration') return formatDuration(side.duration_ms);
  if (field === 'format') return side.format?.toUpperCase() ?? '–';
  if (field === 'quality')
    return side.effective_quality ? t(`library.quality.tiers.${side.effective_quality}`) : '–';
  return side[field];
}
</script>

<style scoped>
.review-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.review-detail__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.review-detail__meta {
  font-size: var(--text-sm);
}

.review-detail__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--weight-bold);
  line-height: 1.3;
}

.review-detail__compare {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin: 0;
}

.review-detail__compare dd,
.review-detail__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.review-detail__facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--space-1) var(--space-3);
  margin: 0;
}

.review-detail__facts dt {
  color: var(--color-text-muted);
}

.review-detail__sides {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.review-detail__sides th,
.review-detail__sides td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--color-divider);
  text-align: left;
}

.review-detail__note {
  margin: 0;
  font-size: var(--text-sm);
}

.review-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.review-detail__actions .q-btn {
  min-height: var(--touch-target);
}

@media (max-width: 599px) {
  .review-detail__compare {
    grid-template-columns: 1fr;
  }
}
</style>
