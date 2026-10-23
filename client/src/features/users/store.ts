import { defineStore } from 'pinia';

import { getServices } from '@/services';

import type { User } from './session';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    deviceId: null as string | null,
    restored: false,
  }),
  getters: {
    signedIn: (state) => state.user !== null,
    isAdmin: (state) => state.user?.role === 'admin',
    canEdit: (state) => state.user?.role === 'admin' || state.user?.role === 'editor',
  },
  actions: {
    bind() {
      const { session } = getServices();
      this.user = session.state.user;
      this.deviceId = session.state.deviceId;
      session.onChange((state) => {
        this.user = state.user;
        this.deviceId = state.deviceId;
      });
    },
    /** Restore the session once per app start (stored refresh token). */
    async restore(): Promise<boolean> {
      if (!this.restored) {
        this.restored = true;
        await getServices().session.restore();
      }
      return this.signedIn;
    },
    setupRequired: () => getServices().session.setupRequired(),
    setup: (account: { username: string; display_name: string; password: string }) =>
      getServices().session.setup(account),
    login: (username: string, password: string) => getServices().session.login(username, password),
    logout: () => getServices().session.logout(),
  },
});
