import type { WorkType } from './api';

/** One icon per work type, always shown with its label. */
export const WORK_ICONS: Record<WorkType, string> = {
  original: 'music_note',
  arrangement: 'tune',
  medley: 'queue_music',
  adaptation: 'transform',
};
