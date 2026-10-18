import { defineStore } from 'pinia';

/**
 * Scroll positions of the library lists for this session (spec: library, Library navigation).
 * Kept in memory only; a list key is the route name plus its parameter.
 */
export const useLibraryPositions = defineStore('libraryPositions', {
  state: (): { positions: Record<string, number> } => ({ positions: {} }),
  actions: {
    position(key: string): number {
      return this.positions[key] ?? 0;
    },
    remember(key: string, position: number): void {
      this.positions[key] = position;
    },
  },
});
