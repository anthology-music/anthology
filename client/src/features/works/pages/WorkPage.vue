<template>
  <q-page class="page">
    <section class="library-section">
      <LibraryBreadcrumb
        :items="[
          { label: t('pages.works.title'), to: { name: 'works' } },
          { label: work?.title ?? '…' },
        ]"
      />
      <MissingEntry v-if="missing" :message="t('works.missing')" />
      <template v-else>
        <header class="library-header">
          <div class="library-header__text">
            <span class="text-muted library-header__kind" data-testid="work-kind">
              <q-icon v-if="work" :name="WORK_ICONS[work.type]" aria-hidden="true" />
              {{ work ? t(`works.types.${work.type}`) : '' }}
              <template v-if="work?.instrumentation"> · {{ work.instrumentation }}</template>
              <template v-if="work?.grade">
                · {{ t('works.gradeShort', { grade: work.grade }) }}
              </template>
              <template v-if="work?.duration_sec">
                · {{ formatDuration(work.duration_sec) }}</template
              >
            </span>
            <h1 class="library-header__title" data-testid="work-title-heading">
              {{ work?.title ?? '…' }}
            </h1>
            <FavoriteButton
              v-if="work"
              :id="workId"
              type="work"
              :name="work.title"
              class="library-header__favorite"
            />
            <p
              v-if="work && work.credits.length"
              class="library-header__meta"
              data-testid="work-credits"
            >
              <span
                v-for="(credit, index) in work.credits"
                :key="`${credit.role}-${credit.person_id}`"
              >
                <template v-if="index">, </template>
                <router-link :to="{ name: 'person', params: { personId: credit.person_id } }">
                  {{ credit.name }}</router-link
                >
                <span class="text-muted"> ({{ t(`works.roles.${credit.role}`) }})</span>
              </span>
            </p>
            <p v-if="work?.iswc" class="text-muted library-header__meta mono">
              ISWC {{ work.iswc }}
            </p>
            <div class="work-page__actions">
              <q-btn
                v-if="playable.length"
                unelevated
                rounded
                no-caps
                color="primary"
                icon="play_arrow"
                :label="t('works.playOriginals')"
                data-testid="work-play-originals"
                @click="player.playTracks(playable)"
              />
              <router-link
                v-if="work && work.recording_count"
                :to="{ name: 'search', query: { q: '', work_id: workId, in: work.title } }"
                data-testid="search-in-work"
              >
                <q-icon name="search" aria-hidden="true" /> {{ t('search.inWork') }}
              </router-link>
              <template v-if="auth.canEdit && work">
                <q-btn
                  outline
                  no-caps
                  icon="edit"
                  :label="t('works.edit')"
                  data-testid="work-edit"
                  @click="editing = true"
                />
                <q-btn
                  flat
                  no-caps
                  icon="delete"
                  :label="t('works.delete')"
                  data-testid="work-delete"
                  @click="confirmDelete = true"
                />
              </template>
            </div>
          </div>
        </header>
        <p v-if="problem" class="work-page__problem" role="alert" data-testid="work-problem">
          {{ t(`works.problem.${problem}`) }}
        </p>

        <section
          v-if="work && (work.type !== 'original' || contents.length)"
          class="work-page__section"
          data-testid="work-contents"
        >
          <h2 class="work-page__heading">
            {{ t('works.originals') }}
            <span class="text-muted work-page__count">
              {{ t('works.originalsCount', { n: contents.length, present: playable.length }) }}
            </span>
          </h2>
          <ol class="work-page__list">
            <li v-for="(row, index) in contents" :key="row.id" class="work-page__row">
              <span class="mono text-muted work-page__position">{{ index + 1 }}</span>
              <q-btn
                v-if="row.track"
                flat
                round
                size="sm"
                icon="play_arrow"
                :aria-label="t('playback.playTrack', { title: row.work.title })"
                :data-testid="`original-play-${row.work.title}`"
                @click="player.playTracks([row.track.id])"
              />
              <span v-else class="work-page__no-play" aria-hidden="true" />
              <WorkRow :work="row.work" class="work-page__work" />
              <QualityBadge
                v-if="row.track"
                :effective="row.track.effective_quality"
                :status="row.track.quality_status"
              />
              <router-link
                v-else
                :to="{ name: 'streaming', query: { source_q: row.acquire_query } }"
                class="work-page__acquire"
                :data-testid="`original-acquire-${row.work.title}`"
              >
                <q-icon name="download" aria-hidden="true" /> {{ t('works.acquire') }}
              </router-link>
              <template v-if="auth.canEdit">
                <q-btn
                  flat
                  round
                  dense
                  icon="arrow_upward"
                  :disable="index === 0"
                  :aria-label="t('works.moveUp', { title: row.work.title })"
                  @click="move(index, -1)"
                />
                <q-btn
                  flat
                  round
                  dense
                  icon="arrow_downward"
                  :disable="index === contents.length - 1"
                  :aria-label="t('works.moveDown', { title: row.work.title })"
                  @click="move(index, 1)"
                />
                <q-btn
                  flat
                  round
                  dense
                  icon="close"
                  :aria-label="t('works.removeOriginal', { title: row.work.title })"
                  @click="act(removeRelation(row.id))"
                />
              </template>
            </li>
          </ol>
          <q-btn
            v-if="auth.canEdit"
            flat
            no-caps
            icon="add"
            :label="t('works.addOriginal')"
            data-testid="original-add"
            @click="addingOriginal = true"
          />
        </section>

        <section class="work-page__section" data-testid="work-recordings">
          <h2 class="work-page__heading">{{ t('works.recordings') }}</h2>
          <p v-if="recordings.length === 0" class="text-muted">{{ t('works.noRecordings') }}</p>
          <ul class="work-page__list">
            <li v-for="row in recordings" :key="row.id" class="work-page__row">
              <PlayableTrackRow
                v-if="row.track"
                :track="row.track"
                context="library"
                class="work-page__work"
              />
              <span v-else class="work-page__work">{{ row.title }} · {{ row.artist }}</span>
              <q-btn
                v-if="auth.canEdit"
                flat
                round
                dense
                icon="link_off"
                :aria-label="t('works.unlink', { title: row.title })"
                @click="act(unlinkRecording(workId, row.recording_id))"
              />
            </li>
          </ul>
          <q-btn
            v-if="auth.canEdit"
            flat
            no-caps
            icon="add_link"
            :label="t('works.linkRecording')"
            data-testid="recording-link"
            @click="linking = true"
          />
        </section>

        <section v-if="containers.length" class="work-page__section" data-testid="work-containers">
          <h2 class="work-page__heading">{{ t('works.containedIn') }}</h2>
          <ul class="work-page__list">
            <li v-for="row in containers" :key="row.id" class="work-page__row">
              <WorkRow :work="row.work" class="work-page__work" />
              <span class="text-muted">{{ t(`works.relations.${row.relation_type}`) }}</span>
            </li>
          </ul>
        </section>
      </template>

      <WorkEditor :open="editing" :work="work" @close="editing = false" @saved="editing = false" />
      <q-dialog v-model="addingOriginal">
        <q-card class="work-page__dialog">
          <q-card-section>
            <SearchPicker
              stream="search.works"
              :label="t('works.findOriginal')"
              testid="pick-work"
              @pick="addOriginal"
            />
          </q-card-section>
        </q-card>
      </q-dialog>
      <q-dialog v-model="linking">
        <q-card class="work-page__dialog">
          <q-card-section>
            <SearchPicker
              stream="search.tracks"
              :label="t('works.findRecording')"
              testid="pick-track"
              @pick="link"
            />
          </q-card-section>
        </q-card>
      </q-dialog>
      <q-dialog v-model="confirmDelete">
        <q-card>
          <q-card-section>{{
            t('works.confirmDelete', { title: work?.title ?? '' })
          }}</q-card-section>
          <q-card-actions align="right">
            <q-btn v-close-popup flat no-caps :label="t('works.cancel')" />
            <q-btn
              unelevated
              no-caps
              color="primary"
              :label="t('works.delete')"
              data-testid="work-delete-confirm"
              @click="remove"
            />
          </q-card-actions>
        </q-card>
      </q-dialog>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import type {
  WorkContainerRow,
  WorkContentRow,
  WorkDetailRow,
  WorkRecordingRow,
} from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import LibraryBreadcrumb from '@/features/library/components/LibraryBreadcrumb.vue';
import MissingEntry from '@/features/library/components/MissingEntry.vue';
import QualityBadge from '@/features/library/components/QualityBadge.vue';
import FavoriteButton from '@/features/personal-data/components/FavoriteButton.vue';
import PlayableTrackRow from '@/features/playback/components/PlayableTrackRow.vue';
import { usePlayerStore } from '@/features/playback/store';
import { useAuthStore } from '@/features/users/store';
import { useSubscription } from '@/sync/useSubscription';

import {
  addRelation,
  deleteWork,
  linkRecording,
  orderRelations,
  type RelationType,
  removeRelation,
  unlinkRecording,
  type WorkProblem,
} from '../api';
import SearchPicker from '../components/SearchPicker.vue';
import WorkEditor from '../components/WorkEditor.vue';
import WorkRow from '../components/WorkRow.vue';
import { formatDuration } from '../duration';
import { WORK_ICONS } from '../icons';

/** One work (spec: works, Navigation between works and recordings): its originals with
 * play and acquire actions, its recordings, the works it is contained in, and editing. */
const props = defineProps<{ workId: string }>();

const LIMIT = 500;
const { t } = useI18n();
const auth = useAuthStore();
const player = usePlayerStore();
const router = useRouter();
const params = { work_id: props.workId };
const header = useSubscription('works.work', params, [0, 1]);
const contentRows = useSubscription('works.work.contents', params, [0, LIMIT]);
const recordingRows = useSubscription('works.work.recordings', params, [0, LIMIT]);
const containerRows = useSubscription('works.work.containers', params, [0, LIMIT]);
const editing = ref(false);
const addingOriginal = ref(false);
const linking = ref(false);
const confirmDelete = ref(false);
const problem = ref<WorkProblem | null>(null);

function loaded<T>(subscription: typeof header): T[] {
  const total = Math.min(subscription.value.total ?? 0, LIMIT);
  return [...Array(total).keys()]
    .map((position) => subscription.value.rows.get(position))
    .filter((row) => row !== undefined) as unknown as T[];
}

const work = computed(() => loaded<WorkDetailRow>(header)[0] ?? null);
const missing = computed(() => header.value.total === 0);
const contents = computed(() => loaded<WorkContentRow>(contentRows));
const recordings = computed(() => loaded<WorkRecordingRow>(recordingRows));
const containers = computed(() => loaded<WorkContainerRow>(containerRows));
const playable = computed(() => contents.value.flatMap((row) => (row.track ? [row.track.id] : [])));

async function act(result: Promise<WorkProblem | null>): Promise<void> {
  problem.value = await result;
}

async function move(index: number, step: number): Promise<void> {
  const ids = contents.value.map((row) => row.id);
  const [moved] = ids.splice(index, 1);
  ids.splice(index + step, 0, moved!);
  await act(orderRelations(props.workId, ids));
}

function relationType(): RelationType {
  if (work.value?.type === 'medley') return 'medley_contains';
  if (work.value?.type === 'original') return 'part_of';
  return 'arrangement_of';
}

async function addOriginal(row: Record<string, unknown>): Promise<void> {
  addingOriginal.value = false;
  await act(addRelation(props.workId, String(row.id), relationType()));
}

async function link(row: Record<string, unknown>): Promise<void> {
  linking.value = false;
  await act(linkRecording(props.workId, String(row.recording_id)));
}

async function remove(): Promise<void> {
  confirmDelete.value = false;
  problem.value = await deleteWork(props.workId);
  if (!problem.value) await router.push({ name: 'works' });
}
</script>

<style scoped>
.work-page__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-3);
}

.work-page__section {
  margin-top: var(--space-5);
}

.work-page__heading {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin: 0 0 var(--space-2);
  font-size: var(--text-lg);
  font-weight: var(--weight-medium);
}

.work-page__count {
  font-size: var(--text-sm);
}

.work-page__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.work-page__row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  border-bottom: 1px solid var(--color-border);
}

.work-page__position {
  width: 2ch;
  text-align: right;
}

.work-page__no-play {
  width: 32px;
}

.work-page__work {
  flex: 1;
  min-width: 0;
}

.work-page__acquire {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  min-height: var(--touch-target);
}

.work-page__problem {
  color: var(--color-status-error);
}

.work-page__dialog {
  width: min(560px, 100vw);
}
</style>
