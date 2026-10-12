import type { Chunk, Delta, ServerMessage, SnapshotMeta } from '@anthology/api-types';

import type { SyncCache } from './cache';
import type { SyncConnection } from './connection';

export interface Row {
  id: string;
  key: unknown[];
  [field: string]: unknown;
}

export type RowSource = 'cache' | 'server';

/** How long to wait before re-requesting the window after order-changing deltas. */
export const REFRESH_DEBOUNCE_MS = 100;

/**
 * One subscription to a stream. Keeps the rows of the loaded windows by position,
 * acknowledges chunks, applies deltas, and resumes after reconnects with `since`.
 *
 * Positions are decided by the server: a delta that only changes data of a loaded row
 * is applied in place; one that changes the order re-requests the window, because the
 * database collation and JavaScript string comparison differ.
 */
export class Subscription {
  total: number | null = null;
  counters: Record<string, number> = {};
  seq: number | null = null;
  source: RowSource | null = null;
  /** Error code from the server, e.g. `unknown_stream` or `forbidden`. */
  error: string | null = null;
  readonly rows = new Map<number, Row>();
  private window: [number, number] = [0, 0];
  /** `subscribe` was sent on the current connection; windows may be sent only then. */
  private active = false;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Set<() => void>();
  private closed = false;

  constructor(
    readonly id: string,
    readonly stream: string,
    readonly params: Record<string, unknown>,
    private readonly connection: SyncConnection,
    private readonly cache: SyncCache | null,
    readonly cacheKey: string,
  ) {}

  onChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Show cached data first; the server's answer replaces it. */
  async loadCached(start: number, end: number): Promise<void> {
    if (!this.cache) return;
    const meta = await this.cache.loadMeta(this.cacheKey);
    if (!meta || this.answered()) return;
    const rows = await this.cache.loadRows(this.cacheKey, start, end);
    if (this.answered()) return;
    this.total = meta.total;
    this.counters = meta.counters;
    this.seq = meta.seq;
    for (const row of rows) this.rows.set(row.position, { id: row.id, ...row.data } as Row);
    this.source = 'cache';
    this.emit();
  }

  get currentWindow(): [number, number] {
    return this.window;
  }

  /** The server has sent a snapshot (cached data must not overwrite it). */
  private answered(): boolean {
    return this.source === 'server';
  }

  setWindow(start: number, end: number): void {
    this.window = [start, end];
    if (this.active) this.connection.send({ type: 'window', sub: this.id, data: { start, end } });
  }

  /** The connection was lost; the next `subscribe` carries the window again. */
  disconnected(): void {
    this.active = false;
  }

  /** (Re-)subscribe on the open connection; resumes from the last known `seq`. */
  subscribe(): void {
    if (this.closed) return;
    const [start, end] = this.window;
    this.active = this.connection.send({
      type: 'subscribe',
      sub: this.id,
      data: { stream: this.stream, params: this.params, start, end, since: this.seq },
    });
  }

  handle(message: ServerMessage): void {
    if (this.closed) return;
    switch (message.type) {
      case 'snapshot_meta':
        this.meta(message);
        break;
      case 'chunk':
        this.chunk(message);
        break;
      case 'delta':
        this.delta(message);
        break;
      case 'resync':
        this.rows.clear();
        void this.cache?.clear(this.cacheKey);
        this.emit();
        break;
      default:
        break;
    }
  }

  /** The server rejected this subscription or one of its requests. */
  fail(code: string): void {
    this.error = code;
    this.emit();
  }

  /** Drop loaded rows outside [start, end) to bound memory while scrolling far. */
  prune(start: number, end: number): void {
    for (const position of [...this.rows.keys()]) {
      if (position < start || position >= end) this.rows.delete(position);
    }
  }

  close(): void {
    this.closed = true;
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    if (this.active) this.connection.send({ type: 'unsubscribe', sub: this.id });
    this.listeners.clear();
  }

  private meta(message: SnapshotMeta): void {
    if (this.source !== 'server') this.rows.clear();
    this.source = 'server';
    this.total = message.data.total;
    this.counters = message.data.counters ?? {};
    this.seq = Math.max(this.seq ?? 0, message.seq);
    for (const position of [...this.rows.keys()]) {
      if (position >= message.data.total) this.rows.delete(position);
    }
    void this.cache?.putMeta({
      subKey: this.cacheKey,
      total: this.total,
      counters: this.counters,
      seq: this.seq,
    });
    this.emit();
  }

  private chunk(message: Chunk): void {
    const { chunk, start, rows } = message.data;
    this.connection.send({ type: 'ack', sub: this.id, data: { chunk } });
    rows.forEach((row, index) => this.rows.set(start + index, row as Row));
    void this.cache?.putRows(
      this.cacheKey,
      start,
      rows.map((row) => ({ id: String(row.id), data: row })),
    );
    this.emit();
  }

  private delta(message: Delta): void {
    const { op, id, key, row, total, counters } = message.data;
    this.seq = Math.max(this.seq ?? 0, message.seq);
    if (total !== null && total !== undefined) this.total = total;
    if (counters) this.counters = counters;
    if (this.total !== null) {
      void this.cache?.putMeta({
        subKey: this.cacheKey,
        total: this.total,
        counters: this.counters,
        seq: this.seq,
      });
    } else {
      void this.cache?.putSeq(this.cacheKey, this.seq);
    }
    const position = this.positionOf(id);
    const loaded = position !== undefined ? this.rows.get(position) : undefined;
    const sameKey = loaded !== undefined && JSON.stringify(loaded.key) === JSON.stringify(key);
    if (op === 'upsert' && row && position !== undefined && sameKey) {
      this.rows.set(position, row as Row);
      void this.cache?.putRows(this.cacheKey, position, [{ id, data: row }]);
    } else {
      this.scheduleRefresh();
    }
    this.emit();
  }

  private positionOf(id: string): number | undefined {
    for (const [position, row] of this.rows) if (row.id === id) return position;
    return undefined;
  }

  private scheduleRefresh(): void {
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => {
      this.refreshTimer = null;
      const [start, end] = this.window;
      this.setWindow(start, end);
    }, REFRESH_DEBOUNCE_MS);
  }

  private emit(): void {
    for (const listener of this.listeners) listener();
  }
}
