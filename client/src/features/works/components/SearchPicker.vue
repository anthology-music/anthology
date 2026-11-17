<template>
  <div class="search-picker">
    <q-input
      v-model="text"
      dense
      outlined
      autofocus
      debounce="250"
      :label="label"
      :data-testid="`${testid}-query`"
    >
      <template #prepend><q-icon name="search" aria-hidden="true" /></template>
    </q-input>
    <PickerResults
      v-if="text.trim()"
      :key="text.trim()"
      :stream="stream"
      :q="text.trim()"
      :testid="testid"
      @pick="(row) => emit('pick', row)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

import PickerResults from './PickerResults.vue';

/** Pick a work or a track by searching (streams ``search.works``, ``search.tracks``). */
defineProps<{ stream: 'search.works' | 'search.tracks'; label: string; testid: string }>();
const emit = defineEmits<{ pick: [row: Record<string, unknown>] }>();
const text = ref('');
</script>
