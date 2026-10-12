import type { ServerMessage } from '@anthology/api-types';

import type { SyncCache } from './cache';
import type { SyncConnection } from './connection';
import { Subscription } from './subscription';

/** Routes messages of one connection to its subscriptions and re-subscribes on reconnect. */
export class SyncClient {
  private readonly subscriptions = new Map<string, Subscription>();
  /** Subscriptions whose cached state has been loaded (only those are sent). */
  private readonly ready = new Set<Subscription>();
  private counter = 0;
  readonly errors: { code: string; sub?: string | null }[] = [];

  constructor(
    readonly connection: SyncConnection,
    private readonly cache: SyncCache | null,
    private readonly scope: () => string,
  ) {
    connection.onMessage((message) => this.route(message));
    connection.onOpen(() => {
      for (const subscription of this.ready) subscription.subscribe();
    });
    connection.onState((state) => {
      if (state !== 'live')
        for (const subscription of this.subscriptions.values()) subscription.disconnected();
    });
  }

  subscribe(
    stream: string,
    params: Record<string, unknown> = {},
    window: [number, number] = [0, 100],
  ): Subscription {
    this.counter += 1;
    const id = `s${this.counter}`;
    const cacheKey = `${this.scope()}|${stream}|${JSON.stringify(params)}`;
    const subscription = new Subscription(
      id,
      stream,
      params,
      this.connection,
      this.cache,
      cacheKey,
    );
    this.subscriptions.set(id, subscription);
    subscription.setWindow(...window);
    // Cached rows first, then subscribe with `since` = the cached change sequence.
    void subscription
      .loadCached(...window)
      .catch(() => undefined)
      .then(() => {
        if (!this.subscriptions.has(id)) return;
        this.ready.add(subscription);
        if (this.connection.state === 'live') subscription.subscribe();
      });
    return subscription;
  }

  unsubscribe(subscription: Subscription): void {
    subscription.close();
    this.subscriptions.delete(subscription.id);
    this.ready.delete(subscription);
  }

  private route(message: ServerMessage): void {
    if (message.type === 'error') {
      this.errors.push({ code: message.data.code, sub: message.sub });
      if (message.sub) this.subscriptions.get(message.sub)?.fail(message.data.code);
      return;
    }
    if ('sub' in message && message.sub) this.subscriptions.get(message.sub)?.handle(message);
  }
}
