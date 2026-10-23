import type { Router } from 'vue-router';

import { useAuthStore } from '@/features/users/store';

/** Pages need a signed-in account; setup and sign-in pages are public. */
export function installAuthGuard(router: Router): void {
  router.beforeEach(async (to) => {
    const auth = useAuthStore();
    const signedIn = await auth.restore();
    if (to.meta.public) {
      return signedIn && (to.name === 'login' || to.name === 'setup') ? { name: 'local' } : true;
    }
    if (signedIn) return to.meta.editors && !auth.canEdit ? { name: 'local' } : true;
    try {
      if (await auth.setupRequired()) return { name: 'setup' };
    } catch {
      // Server unreachable: the sign-in page shows the error when submitting.
    }
    return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } };
  });
}

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean;
    /** Only for editors and admins. */
    editors?: boolean;
  }
}
