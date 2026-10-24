import { computed, reactive } from 'vue';

import type { Schemas } from '@anthology/api-types';

export type EditRule = Schemas['EditRule'];
export type TrackSelection = { ids: string[] } | { rule: EditRule };

/**
 * The tracks selected in edit mode: single rows (shift-click selects the range of loaded rows
 * since the last click) or the whole list, sent as its rule (AGENTS.md: rules, not IDs).
 */
export function useSelection(rule: () => EditRule, total: () => number | null) {
  const state = reactive({ ids: new Set<string>(), all: false, anchor: null as number | null });

  function toggle(
    id: string,
    position: number,
    shift: boolean,
    rowAt: (position: number) => { id: string } | undefined,
  ): void {
    if (state.all) {
      state.all = false;
      state.ids.clear();
    }
    if (shift && state.anchor !== null) {
      const [from, to] = [Math.min(state.anchor, position), Math.max(state.anchor, position)];
      for (let index = from; index <= to; index += 1) {
        const row = rowAt(index);
        if (row) state.ids.add(row.id);
      }
    } else if (state.ids.has(id)) {
      state.ids.delete(id);
    } else {
      state.ids.add(id);
    }
    state.anchor = position;
  }

  function selectAll(): void {
    state.all = true;
    state.ids.clear();
  }

  function clear(): void {
    state.all = false;
    state.ids.clear();
    state.anchor = null;
  }

  const count = computed(() => (state.all ? (total() ?? 0) : state.ids.size));
  const selection = computed<TrackSelection>(() =>
    state.all ? { rule: rule() } : { ids: [...state.ids] },
  );
  const selected = (id: string) => state.all || state.ids.has(id);

  return { state, toggle, selectAll, clear, count, selection, selected };
}

export type Selection = ReturnType<typeof useSelection>;
