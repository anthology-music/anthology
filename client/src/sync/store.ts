import { defineStore } from 'pinia';

import { getServices } from '@/services';

import type { ConnectionState } from './connection';

/** The connection state for the UI. */
export const useSyncStore = defineStore('sync', {
  state: (): { connection: ConnectionState } => ({ connection: 'offline' }),
  actions: {
    bind() {
      const { connection } = getServices().sync;
      this.connection = connection.state;
      connection.onState((state) => {
        this.connection = state;
      });
    },
  },
});
