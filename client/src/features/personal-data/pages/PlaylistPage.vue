<template>
  <section class="library-section">
    <MissingEntry v-if="missing" :message="t('personal.playlists.missing')" />
    <template v-else>
      <header class="library-header">
        <div class="library-header__text">
          <span class="text-muted library-header__kind">
            {{ t('personal.playlists.kind') }} ·
            {{ t(`personal.visibility.${playlist?.visibility ?? 'private'}`) }}
          </span>
          <h1 class="library-header__title" data-testid="playlist-title">
            {{ playlist?.name ?? '…' }}
          </h1>
          <p v-if="playlist" class="library-header__meta" data-testid="playlist-meta">
            {{ playlist.owner_name }} · {{ count('tracks', playlist.entry_count) }} ·
            {{ formatDuration(playlist.duration_ms) }}
          </p>
          <span class="playlist__buttons">
            <q-btn
              v-if="playlist && playlist.entry_count"
              unelevated
              rounded
              no-caps
              color="primary"
              icon="play_arrow"
              :label="t('personal.playlists.play')"
              data-testid="playlist-play"
              @click="player.playList({ list: 'playlist', playlist_id: playlistId })"
            />
            <q-btn
              v-if="playlist"
              outline
              rounded
              no-caps
              icon="download"
              :label="t('personal.playlists.export')"
              data-testid="playlist-export"
              @click="download"
            />
            <template v-if="playlist?.mine">
              <q-toggle
                :model-value="playlist.visibility === 'shared'"
                :label="t('personal.playlists.share')"
                data-testid="playlist-share"
                @update:model-value="(on: boolean) => share(on)"
              />
              <q-btn
                flat
                no-caps
                icon="edit"
                :label="t('personal.playlists.rename')"
                data-testid="playlist-rename"
                @click="newName = playlist.name"
              />
              <q-btn
                flat
                no-caps
                icon="delete"
                :label="t('personal.playlists.delete')"
                data-testid="playlist-delete"
                @click="confirming = true"
              />
            </template>
          </span>
        </div>
      </header>
      <form v-if="newName !== null" class="playlist__rename" @submit.prevent="rename">
        <q-input
          v-model="newName"
          dense
          outlined
          autofocus
          :label="t('personal.playlists.rename')"
          data-testid="playlist-name"
        />
        <q-btn type="submit" unelevated color="primary" :label="t('personal.playlists.save')" />
        <q-btn flat :label="t('personal.playlists.cancel')" @click="newName = null" />
      </form>
      <q-dialog v-model="confirming">
        <q-card data-testid="playlist-confirm-delete">
          <q-card-section>
            {{ t('personal.playlists.confirmDelete', { name: playlist?.name ?? '' }) }}
          </q-card-section>
          <q-card-actions align="right">
            <q-btn v-close-popup flat :label="t('personal.playlists.cancel')" />
            <q-btn
              v-close-popup
              unelevated
              color="negative"
              :label="t('personal.playlists.delete')"
              data-testid="playlist-confirm"
              @click="remove"
            />
          </q-card-actions>
        </q-card>
      </q-dialog>
      <p v-if="lastEdit" class="playlist__edit" role="status" data-testid="playlist-edit">
        {{ t(`personal.edits.${lastEdit.kind}`, { n: lastEdit.count }) }}
        <q-btn
          flat
          dense
          no-caps
          :label="t('personal.edits.undo')"
          data-testid="playlist-undo"
          @click="undo"
        />
      </p>
      <p v-if="problem" class="playlist__problem" role="alert" data-testid="playlist-problem">
        {{ t(`personal.problem.${problem}`) }}
      </p>
      <LibraryList
        v-if="playlist"
        :key="playlist.generation"
        stream="personal.playlist.entries"
        :params="{ playlist_id: playlistId, generation: playlist.generation }"
        :position-key="`playlist:${playlistId}`"
        :label="t('personal.playlists.entriesOf', { name: playlist.name })"
        :empty="t('personal.playlists.noEntries')"
        uncached
      >
        <template #default="{ row, position, rowAt }">
          <PlaylistEntryRow
            :entry="row as unknown as PlaylistEntryRowType"
            :first="position === 0"
            :last="position === playlist.entry_count - 1"
            @play="playFrom(String((row as unknown as PlaylistEntryRowType).track.id))"
            @remove="removeEntry(String(row.id))"
            @up="moveTo(String(row.id), position - 2, rowAt)"
            @down="moveTo(String(row.id), position + 1, rowAt)"
            @drop="(dragged: string) => drop(dragged, String(row.id))"
          />
        </template>
      </LibraryList>
    </template>
  </section>
</template>

<script setup lang="ts">
import type { PlaylistEntryRow as PlaylistEntryRowType } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import LibraryList from '@/features/library/components/LibraryList.vue';
import MissingEntry from '@/features/library/components/MissingEntry.vue';
import { formatDuration } from '@/features/library/format';
import { useCounts } from '@/features/library/numbers';
import { usePlayerStore } from '@/features/playback/store';

import {
  deletePlaylist,
  exportPlaylist,
  moveEntries,
  type PlaylistProblem,
  removeEntries,
  undoEdit,
  updatePlaylist,
} from '../api';
import PlaylistEntryRow from '../components/PlaylistEntryRow.vue';
import { usePlaylists } from '../playlists';

/** One playlist: its entries in order, with who added them; everyone who sees a shared
 * playlist edits it, the last edit can be undone (spec: personal-data). */
const props = defineProps<{ playlistId: string }>();

const { t } = useI18n();
const { count } = useCounts();
const router = useRouter();
const player = usePlayerStore();
const { playlists } = usePlaylists();
const playlist = computed(() => playlists.value.find((row) => row.id === props.playlistId));
const loaded = ref(false);
const missing = computed(() => loaded.value && !playlist.value);
setTimeout(() => (loaded.value = true), 3_000);
const problem = ref<PlaylistProblem | null>(null);
const newName = ref<string | null>(null);
const confirming = ref(false);
const lastEdit = ref<{ id: string; kind: 'add' | 'remove' | 'move'; count: number } | null>(null);

function edited(
  result: { editId: string | null; problem: PlaylistProblem | null },
  kind: 'remove' | 'move',
  n = 1,
) {
  problem.value = result.problem;
  lastEdit.value = result.editId ? { id: result.editId, kind, count: n } : null;
}

async function removeEntry(entryId: string): Promise<void> {
  edited(await removeEntries(props.playlistId, [entryId]), 'remove');
}

/** Move behind the entry at ``position`` (before the first: to the start). */
async function moveTo(
  entryId: string,
  position: number,
  rowAt: (position: number) => Record<string, unknown> | undefined,
): Promise<void> {
  const after = position < 0 ? null : (rowAt(position)?.id as string | undefined);
  if (position >= 0 && !after) return;
  edited(await moveEntries(props.playlistId, [entryId], after ?? null), 'move');
}

async function drop(dragged: string, target: string): Promise<void> {
  if (dragged === target) return;
  edited(await moveEntries(props.playlistId, [dragged], target), 'move');
}

async function undo(): Promise<void> {
  if (!lastEdit.value) return;
  problem.value = await undoEdit(lastEdit.value.id);
  lastEdit.value = null;
}

async function playFrom(trackId: string): Promise<void> {
  await player.playList({ list: 'playlist', playlist_id: props.playlistId }, trackId);
}

async function share(on: boolean): Promise<void> {
  problem.value = await updatePlaylist(props.playlistId, {
    visibility: on ? 'shared' : 'private',
  });
}

async function rename(): Promise<void> {
  const name = newName.value?.trim();
  if (!name) return;
  problem.value = await updatePlaylist(props.playlistId, { name });
  if (!problem.value) newName.value = null;
}

async function remove(): Promise<void> {
  problem.value = await deletePlaylist(props.playlistId);
  if (!problem.value) await router.push({ name: 'playlists' });
}

async function download(): Promise<void> {
  const blob = await exportPlaylist(props.playlistId);
  if (!blob) {
    problem.value = 'failed';
    return;
  }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${playlist.value?.name ?? 'playlist'}.m3u8`;
  link.click();
  URL.revokeObjectURL(link.href);
}
</script>

<style scoped>
.playlist__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
}

.playlist__rename {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin: 0 0 var(--space-3);
}

.playlist__edit {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 0 var(--space-2);
}

.playlist__problem {
  margin: 0 0 var(--space-2);
  color: var(--color-status-error);
}
</style>
