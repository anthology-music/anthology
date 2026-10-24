<template>
  <section class="library-section">
    <div class="library-section__heading">
      <h1 class="library-section__title">{{ t('library.sections.tracks') }}</h1>
      <EditModeSwitch v-if="auth.canEdit" v-model="editing" />
    </div>
    <EditBar v-if="editing" :selection="selection" />
    <LibraryList
      ref="list"
      stream="library.tracks"
      position-key="library-tracks"
      :label="t('library.sections.tracks')"
      :empty="t('library.empty.tracks')"
    >
      <template #default="{ row, position, rowAt }">
        <SelectableRow
          v-if="editing"
          :id="String(row.id)"
          :selected="selection.selected(String(row.id))"
          :label="t('tagging.select', { name: String(row.title) })"
          @toggle="
            (shift) =>
              selection.toggle(
                String(row.id),
                position,
                shift,
                (p) => rowAt(p) as { id: string } | undefined,
              )
          "
        >
          <TrackRow :track="row as unknown as LibraryTrackRow" context="library" />
        </SelectableRow>
        <TrackRow v-else :track="row as unknown as LibraryTrackRow" context="library" />
      </template>
    </LibraryList>
  </section>
</template>

<script setup lang="ts">
import type { LibraryTrackRow } from '@anthology/api-types';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import EditBar from '@/features/tagging/components/EditBar.vue';
import EditModeSwitch from '@/features/tagging/components/EditModeSwitch.vue';
import SelectableRow from '@/features/tagging/components/SelectableRow.vue';
import { useSelection } from '@/features/tagging/selection';
import { useAuthStore } from '@/features/users/store';

import LibraryList from '../components/LibraryList.vue';
import TrackRow from '../components/TrackRow.vue';

const { t } = useI18n();
const auth = useAuthStore();
const editing = ref(false);
const list = ref<InstanceType<typeof LibraryList> | null>(null);
const selection = useSelection(
  () => ({ list: 'tracks' }),
  () => list.value?.total() ?? null,
);
</script>
