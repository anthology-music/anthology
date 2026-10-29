<template>
  <section class="library-section">
    <h1 class="library-section__title">{{ t('personal.playlists.title') }}</h1>
    <div class="playlists__actions">
      <form class="playlists__form" @submit.prevent="create">
        <q-input
          v-model="name"
          dense
          outlined
          :label="t('personal.playlists.newName')"
          data-testid="playlist-new-name"
        />
        <q-btn
          type="submit"
          unelevated
          color="primary"
          :disable="!name.trim()"
          :label="t('personal.playlists.create')"
          data-testid="playlist-create"
        />
      </form>
      <form class="playlists__form" @submit.prevent="addFolder">
        <q-input
          v-model="folderName"
          dense
          outlined
          :label="t('personal.playlists.newFolder')"
          data-testid="folder-new-name"
        />
        <q-btn
          type="submit"
          outline
          :disable="!folderName.trim()"
          :label="t('personal.playlists.createFolder')"
          data-testid="folder-create"
        />
      </form>
      <label class="playlists__import">
        <q-icon name="upload_file" aria-hidden="true" /> {{ t('personal.playlists.import') }}
        <input
          type="file"
          accept=".m3u,.m3u8,.pls,.xspf,audio/x-mpegurl,application/xspf+xml"
          class="playlists__file"
          data-testid="playlist-import"
          @change="importFile"
        />
      </label>
    </div>
    <p v-if="imported" class="playlists__notice" role="status" data-testid="playlist-imported">
      {{ t('personal.playlists.imported', { n: imported.entries }) }}
      <template v-if="imported.unmatched.length">
        {{ t('personal.playlists.unmatched', { n: imported.unmatched.length }) }}
        <span class="text-muted">{{ imported.unmatched.slice(0, 5).join(' · ') }}</span>
      </template>
    </p>
    <p v-if="problem" class="playlists__problem" role="alert">
      {{ t(`personal.problem.${problem}`) }}
    </p>

    <section v-for="group in groups" :key="group.key" class="playlists__group">
      <h2 class="playlists__group-title">
        <q-icon :name="group.icon" aria-hidden="true" /> {{ group.title }}
        <q-btn
          v-if="group.folderId"
          flat
          dense
          round
          size="sm"
          icon="delete"
          :aria-label="t('personal.playlists.deleteFolder', { name: group.title })"
          @click="removeFolder(group.folderId)"
        />
      </h2>
      <ul class="item-list">
        <li v-for="playlist in group.playlists" :key="playlist.id" class="item-list__row">
          <router-link
            :to="{ name: 'playlist', params: { playlistId: playlist.id } }"
            class="playlists__link"
            :data-testid="`playlist-${playlist.name}`"
          >
            <q-icon
              :name="playlist.visibility === 'shared' ? 'group' : 'lock'"
              :aria-label="t(`personal.visibility.${playlist.visibility}`)"
            />
            <span class="item-list__main">
              <span>{{ playlist.name }}</span>
              <span class="text-muted item-list__sub">
                {{ count('tracks', playlist.entry_count) }} ·
                {{ formatDuration(playlist.duration_ms) }}
                <template v-if="!playlist.mine"> · {{ playlist.owner_name }}</template>
              </span>
            </span>
          </router-link>
          <select
            v-if="playlist.mine && folders.length"
            class="playlists__folder"
            :value="playlist.folder_id ?? ''"
            :aria-label="t('personal.playlists.folderOf', { name: playlist.name })"
            @change="move(playlist.id, ($event.target as HTMLSelectElement).value || null)"
          >
            <option value="">{{ t('personal.playlists.noFolder') }}</option>
            <option v-for="folder in folders" :key="folder.id" :value="folder.id">
              {{ folder.name }}
            </option>
          </select>
        </li>
      </ul>
    </section>
    <p v-if="playlists.length === 0" class="text-muted" data-testid="playlists-empty">
      {{ t('personal.playlists.empty') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import type { PlaylistRow } from '@anthology/api-types';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import { formatDuration } from '@/features/library/format';
import { useCounts } from '@/features/library/numbers';

import {
  createFolder,
  createPlaylist,
  deleteFolder,
  type Imported,
  importPlaylist,
  type PlaylistProblem,
  updatePlaylist,
} from '../api';
import { usePlaylists } from '../playlists';

/** Own playlists by folder, then the playlists other users share (spec: personal-data,
 * Playlist folders, Playlist ownership and visibility). */
const { t } = useI18n();
const { count } = useCounts();
const router = useRouter();
const { playlists, folders } = usePlaylists();
const name = ref('');
const folderName = ref('');
const imported = ref<Imported | null>(null);
const problem = ref<PlaylistProblem | null>(null);

interface Group {
  key: string;
  title: string;
  icon: string;
  folderId: string | null;
  playlists: PlaylistRow[];
}

const groups = computed<Group[]>(() => {
  const own = playlists.value.filter((playlist) => playlist.mine);
  const result: Group[] = folders.value.map((folder) => ({
    key: folder.id,
    title: folder.name,
    icon: 'folder',
    folderId: folder.id,
    playlists: own.filter((playlist) => playlist.folder_id === folder.id),
  }));
  const loose = own.filter((playlist) => !playlist.folder_id);
  if (loose.length)
    result.push({
      key: 'own',
      title: t('personal.playlists.mine'),
      icon: 'queue_music',
      folderId: null,
      playlists: loose,
    });
  const others = playlists.value.filter((playlist) => !playlist.mine);
  if (others.length)
    result.push({
      key: 'shared',
      title: t('personal.playlists.sharedWithMe'),
      icon: 'group',
      folderId: null,
      playlists: others,
    });
  return result;
});

async function create(): Promise<void> {
  const id = await createPlaylist(name.value.trim());
  if (!id) {
    problem.value = 'failed';
    return;
  }
  name.value = '';
  await router.push({ name: 'playlist', params: { playlistId: id } });
}

async function addFolder(): Promise<void> {
  if (await createFolder(folderName.value.trim())) folderName.value = '';
  else problem.value = 'failed';
}

async function removeFolder(folderId: string): Promise<void> {
  if (!(await deleteFolder(folderId))) problem.value = 'failed';
}

async function move(playlistId: string, folderId: string | null): Promise<void> {
  problem.value = await updatePlaylist(playlistId, { folder_id: folderId });
}

async function importFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const result = await importPlaylist(file.name.replace(/\.[^.]+$/, '') || file.name, file);
  input.value = '';
  if (typeof result === 'string') {
    problem.value = result;
    imported.value = null;
  } else {
    problem.value = null;
    imported.value = result;
  }
}
</script>

<style scoped>
.playlists__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: center;
  margin-bottom: var(--space-4);
}

.playlists__form {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.playlists__import {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: var(--touch-target);
  color: var(--color-accent-strong);
  cursor: pointer;
}

.playlists__import:focus-within {
  outline: 2px solid var(--color-selection-ring);
}

.playlists__file {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}

.playlists__group-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--text-md);
}

.playlists__link {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  color: inherit;
  text-decoration: none;
}

.playlists__folder {
  min-height: var(--touch-target);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.playlists__notice {
  margin: 0 0 var(--space-3);
}

.playlists__problem {
  margin: 0 0 var(--space-3);
  color: var(--color-status-error);
}
</style>
