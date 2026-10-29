<template>
  <q-card class="add-to-playlist" data-testid="add-to-playlist">
    <q-card-section>
      <h2 class="add-to-playlist__title">{{ t('personal.playlists.addTitle') }}</h2>
    </q-card-section>
    <q-list class="add-to-playlist__list">
      <q-item
        v-for="playlist in playlists"
        :key="playlist.id"
        clickable
        :disable="busy"
        :data-testid="`add-to-${playlist.name}`"
        @click="add(playlist.id, playlist.name)"
      >
        <q-item-section avatar>
          <q-icon :name="playlist.visibility === 'shared' ? 'group' : 'queue_music'" />
        </q-item-section>
        <q-item-section>
          <q-item-label>{{ playlist.name }}</q-item-label>
          <q-item-label v-if="!playlist.mine" caption>{{ playlist.owner_name }}</q-item-label>
        </q-item-section>
      </q-item>
    </q-list>
    <q-card-section>
      <form class="add-to-playlist__new" @submit.prevent="addToNew">
        <q-input
          v-model="name"
          dense
          outlined
          :label="t('personal.playlists.newName')"
          data-testid="add-to-new-name"
        />
        <q-btn
          type="submit"
          unelevated
          color="primary"
          :disable="!name.trim() || busy"
          :label="t('personal.playlists.createAndAdd')"
          data-testid="add-to-new"
        />
      </form>
      <p v-if="problem" class="add-to-playlist__problem" role="alert">
        {{ t(`personal.problem.${problem}`) }}
      </p>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import type { Schemas } from '@anthology/api-types';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import { addToPlaylist, createPlaylist, type PlaylistProblem } from '../api';
import { usePlaylists } from '../playlists';

/** Add tracks (``ids``) or the tracks of a list (``rule``) to a playlist the user may edit:
 * an own one or a shared one (spec: personal-data, Shared playlists are editable by all). */
const props = defineProps<{ ids?: string[]; rule?: Schemas['EntriesIn']['rule'] }>();
const emit = defineEmits<{ added: [name: string, editId: string | null] }>();

const { t } = useI18n();
const { playlists } = usePlaylists();
const name = ref('');
const busy = ref(false);
const problem = ref<PlaylistProblem | null>(null);

async function add(playlistId: string, playlistName: string): Promise<void> {
  busy.value = true;
  const result = await addToPlaylist(playlistId, {
    ids: props.ids ?? null,
    rule: props.rule ?? null,
    at_start: false,
  });
  busy.value = false;
  problem.value = result.problem;
  if (!result.problem) emit('added', playlistName, result.editId);
}

async function addToNew(): Promise<void> {
  busy.value = true;
  const id = await createPlaylist(name.value.trim());
  busy.value = false;
  if (id) await add(id, name.value.trim());
  else problem.value = 'failed';
}
</script>

<style scoped>
.add-to-playlist {
  width: min(420px, 100vw);
}

.add-to-playlist__title {
  margin: 0;
  font-size: var(--text-lg);
}

.add-to-playlist__list {
  max-height: 50vh;
  overflow-y: auto;
}

.add-to-playlist__new {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.add-to-playlist__problem {
  margin: var(--space-2) 0 0;
  color: var(--color-status-error);
}
</style>
