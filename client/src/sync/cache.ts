import Dexie, { type Table } from 'dexie';

export interface CachedRow {
  subKey: string;
  position: number;
  id: string;
  data: Record<string, unknown>;
}

export interface CachedMeta {
  subKey: string;
  total: number;
  counters: Record<string, number>;
  seq: number;
}

/**
 * Local cache of subscriptions in IndexedDB, so lists show data within 300 ms
 * (spec: sync-protocol, interaction budget) and resume with `since`.
 */
export class SyncCache extends Dexie {
  rows!: Table<CachedRow, [string, number]>;
  meta!: Table<CachedMeta, string>;

  constructor(name = 'anthology-sync') {
    super(name);
    this.version(1).stores({
      rows: '[subKey+position], subKey',
      meta: 'subKey',
    });
  }

  loadMeta(subKey: string): Promise<CachedMeta | undefined> {
    return this.meta.get(subKey);
  }

  loadRows(subKey: string, start: number, end: number): Promise<CachedRow[]> {
    return this.rows
      .where('[subKey+position]')
      .between([subKey, start], [subKey, end], true, false)
      .toArray();
  }

  async putMeta(meta: CachedMeta): Promise<void> {
    await this.transaction('rw', this.meta, this.rows, async () => {
      await this.meta.put(meta);
      await this.rows
        .where('[subKey+position]')
        .between([meta.subKey, meta.total], [meta.subKey, Dexie.maxKey], true, true)
        .delete();
    });
  }

  async putRows(
    subKey: string,
    start: number,
    rows: { id: string; data: Record<string, unknown> }[],
  ) {
    await this.rows.bulkPut(
      rows.map((row, index) => ({ subKey, position: start + index, id: row.id, data: row.data })),
    );
  }

  async putSeq(subKey: string, seq: number): Promise<void> {
    await this.meta.update(subKey, { seq });
  }

  async clear(subKey: string): Promise<void> {
    await this.transaction('rw', this.meta, this.rows, async () => {
      await this.meta.delete(subKey);
      await this.rows.where('subKey').equals(subKey).delete();
    });
  }
}
