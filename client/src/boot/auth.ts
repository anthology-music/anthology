import { defineBoot } from '#q-app';

import { useAuthStore } from '@/features/users/store';
import { useSyncStore } from '@/sync/store';

export default defineBoot(() => {
  useAuthStore().bind();
  useSyncStore().bind();
});
