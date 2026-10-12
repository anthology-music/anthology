import { PROTOCOL_VERSION, type ClientMessage, type ServerMessage } from '@anthology/api-types';

/** The quiet connection state shown in the UI (client/AGENTS.md). */
export type ConnectionState = 'offline' | 'connecting' | 'live' | 'reconnecting' | 'outdated';

/** The subset of the browser WebSocket the connection uses (replaceable in tests). */
export interface SocketLike {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
}

export type SocketFactory = (url: string) => SocketLike;

export interface TokenSource {
  accessToken(): Promise<string | null>;
  refresh(): Promise<void>;
  onToken(listener: (token: string) => void): () => void;
}

export const CLOSE_TOKEN_EXPIRED = 4401;
export const CLOSE_UNSUPPORTED_PROTOCOL = 4426;
const CLOSE_NORMAL = 1000;

export interface ConnectionOptions {
  url: string;
  tokens: TokenSource;
  deviceId?: () => string | null;
  socketFactory?: SocketFactory;
  minDelayMs?: number;
  maxDelayMs?: number;
  random?: () => number;
}

/**
 * One WebSocket per client (spec: sync-protocol). Sends `hello` with the access token,
 * renews it with `auth`, reconnects with exponential backoff and handles the close codes:
 * 4401 → refresh the token and reconnect, 4426 → stop (the app must be updated).
 */
export class SyncConnection {
  private socket: SocketLike | null = null;
  private stateValue: ConnectionState = 'offline';
  private attempts = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  private readonly stateListeners = new Set<(state: ConnectionState) => void>();
  private readonly messageListeners = new Set<(message: ServerMessage) => void>();
  private readonly openListeners = new Set<() => void>();
  private unsubscribeToken: (() => void) | null = null;

  constructor(private readonly options: ConnectionOptions) {}

  get state(): ConnectionState {
    return this.stateValue;
  }

  onState(listener: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  onMessage(listener: (message: ServerMessage) => void): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  /** Called after every successful `welcome` (subscriptions re-subscribe here). */
  onOpen(listener: () => void): () => void {
    this.openListeners.add(listener);
    return () => this.openListeners.delete(listener);
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.unsubscribeToken = this.options.tokens.onToken((token) => {
      if (this.stateValue === 'live') this.send({ type: 'auth', data: { token } });
    });
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.unsubscribeToken?.();
    this.unsubscribeToken = null;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close(CLOSE_NORMAL);
    this.setState('offline');
  }

  send(message: ClientMessage): boolean {
    if (this.stateValue !== 'live' || !this.socket) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  private connect(): void {
    if (this.stopped) return;
    this.setState(this.attempts === 0 ? 'connecting' : 'reconnecting');
    // The browser WebSocket satisfies SocketLike at runtime; only its event types are richer.
    const factory =
      this.options.socketFactory ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
    const socket = factory(this.options.url);
    this.socket = socket;

    socket.onopen = () => void this.hello(socket);
    socket.onmessage = (event: { data: unknown }) => this.receive(event.data);
    socket.onclose = (event: { code: number }) => {
      if (this.socket !== socket) return;
      this.socket = null;
      void this.closed(event.code);
    };
  }

  private async hello(socket: SocketLike): Promise<void> {
    const token = await this.options.tokens.accessToken().catch(() => null);
    if (this.socket !== socket) return;
    if (!token) {
      this.stop();
      return;
    }
    socket.send(
      JSON.stringify({
        type: 'hello',
        data: {
          protocol: PROTOCOL_VERSION,
          token,
          device_id: this.options.deviceId?.() ?? null,
        },
      } satisfies ClientMessage),
    );
  }

  private receive(data: unknown): void {
    let message: ServerMessage;
    try {
      message = JSON.parse(String(data)) as ServerMessage;
    } catch {
      return;
    }
    if (message.type === 'welcome') {
      this.attempts = 0;
      this.setState('live');
      for (const listener of this.openListeners) listener();
      return;
    }
    for (const listener of this.messageListeners) listener(message);
  }

  private async closed(code: number): Promise<void> {
    if (this.stopped) return;
    if (code === CLOSE_UNSUPPORTED_PROTOCOL) {
      this.stopped = true;
      this.setState('outdated');
      return;
    }
    if (code === CLOSE_TOKEN_EXPIRED) {
      try {
        await this.options.tokens.refresh();
      } catch {
        // Signed out (refresh rejected) or server unreachable: back off and retry;
        // a signed-out session makes `hello` stop the connection.
        this.schedule();
        return;
      }
      this.attempts = Math.max(this.attempts, 1);
      this.connect();
      return;
    }
    this.schedule();
  }

  private schedule(): void {
    this.attempts += 1;
    this.setState('reconnecting');
    const min = this.options.minDelayMs ?? 500;
    const max = this.options.maxDelayMs ?? 30_000;
    const base = Math.min(max, min * 2 ** (this.attempts - 1));
    const jitter = 0.5 + (this.options.random ?? Math.random)() / 2;
    this.timer = setTimeout(() => this.connect(), base * jitter);
  }

  private setState(state: ConnectionState): void {
    if (state === this.stateValue) return;
    this.stateValue = state;
    for (const listener of this.stateListeners) listener(state);
  }
}
