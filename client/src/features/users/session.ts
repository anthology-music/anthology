import type { Schemas } from '@anthology/api-types';
import createClient from 'openapi-fetch';
import type { paths } from '@anthology/api-types';

import { describeDevice } from '@/platform/device';
import type { KeyValueStorage } from '@/platform/storage';

export type User = Schemas['UserOut'];
type TokenResponse = Schemas['TokenResponse'];

const REFRESH_TOKEN = 'anthology.refreshToken';
const DEVICE_ID = 'anthology.deviceId';
/** Refresh the access token this long before it expires. */
export const REFRESH_MARGIN_MS = 60_000;

export class AuthError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

export interface SessionState {
  user: User | null;
  deviceId: string | null;
}

type Listener = (state: SessionState) => void;
type TokenListener = (accessToken: string) => void;

/**
 * Sign-in state of this client: access token in memory, refresh token and device ID in
 * storage. Refreshes are single-flight, because the server signs a device out when a
 * refresh token is used twice (spec: users, refresh token rotation).
 */
export class AuthSession {
  private accessTokenValue: string | null = null;
  private expiresAt = 0;
  private refreshing: Promise<void> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private listeners = new Set<Listener>();
  private tokenListeners = new Set<TokenListener>();
  readonly state: SessionState = { user: null, deviceId: null };
  private readonly client;

  constructor(
    private readonly storage: KeyValueStorage,
    private readonly options: { baseUrl?: string; fetch?: typeof fetch; now?: () => number } = {},
  ) {
    this.client = createClient<paths>({
      baseUrl: options.baseUrl ?? '',
      fetch: options.fetch ?? ((request: Request) => globalThis.fetch(request)),
    });
    this.state.deviceId = storage.get(DEVICE_ID);
  }

  private now(): number {
    return this.options.now?.() ?? Date.now();
  }

  get signedIn(): boolean {
    return this.state.user !== null;
  }

  onChange(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Called with every new access token (the sync connection sends it as `auth`). */
  onToken(listener: TokenListener): () => void {
    this.tokenListeners.add(listener);
    return () => this.tokenListeners.delete(listener);
  }

  /** Restore a session from the stored refresh token; returns whether signed in. */
  async restore(): Promise<boolean> {
    if (!this.storage.get(REFRESH_TOKEN)) return false;
    try {
      await this.refresh();
      return true;
    } catch {
      return false;
    }
  }

  async setupRequired(): Promise<boolean> {
    const { data, error } = await this.client.GET('/api/v1/setup');
    if (error || !data) throw new AuthError('server_unreachable');
    return data.required;
  }

  async setup(account: { username: string; display_name: string; password: string }) {
    const { data, error, response } = await this.client.POST('/api/v1/setup', {
      body: { ...account, device: this.device() },
    });
    if (error || !data)
      throw new AuthError(response.status === 409 ? 'setup_not_allowed' : 'failed');
    this.apply(data);
  }

  async login(username: string, password: string): Promise<void> {
    const { data, error, response } = await this.client.POST('/api/v1/auth/login', {
      body: { username, password, device: this.device() },
    });
    if (error || !data) {
      throw new AuthError(response.status === 401 ? 'invalid_credentials' : 'failed');
    }
    this.apply(data);
  }

  async logout(): Promise<void> {
    const token = this.accessTokenValue;
    this.clear();
    if (token) {
      await this.client
        .POST('/api/v1/auth/logout', { headers: { Authorization: `Bearer ${token}` } })
        .catch(() => undefined);
    }
  }

  /** A valid access token; refreshes first if it expires within the margin. */
  async accessToken(): Promise<string | null> {
    if (!this.signedIn && !this.storage.get(REFRESH_TOKEN)) return null;
    if (!this.accessTokenValue || this.expiresAt - this.now() < REFRESH_MARGIN_MS) {
      await this.refresh();
    }
    return this.accessTokenValue;
  }

  /** Exchange the refresh token; concurrent callers share one request. */
  refresh(): Promise<void> {
    this.refreshing ??= this.doRefresh().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  private async doRefresh(): Promise<void> {
    const refreshToken = this.storage.get(REFRESH_TOKEN);
    if (!refreshToken) {
      this.clear();
      throw new AuthError('signed_out');
    }
    const { data, response } = await this.client.POST('/api/v1/auth/refresh', {
      body: { refresh_token: refreshToken },
    });
    if (!data) {
      if (response.status === 401) this.clear();
      throw new AuthError(response.status === 401 ? 'signed_out' : 'server_unreachable');
    }
    this.apply(data);
  }

  private device(): Schemas['DeviceIn'] {
    return { ...describeDevice(), id: this.state.deviceId };
  }

  private apply(tokens: TokenResponse): void {
    this.accessTokenValue = tokens.access_token;
    this.expiresAt = Date.parse(tokens.expires_at);
    this.storage.set(REFRESH_TOKEN, tokens.refresh_token);
    this.storage.set(DEVICE_ID, tokens.device_id);
    this.state.user = tokens.user;
    this.state.deviceId = tokens.device_id;
    this.schedule();
    this.emit();
    for (const listener of this.tokenListeners) listener(tokens.access_token);
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    const delay = Math.max(this.expiresAt - this.now() - REFRESH_MARGIN_MS, 1_000);
    this.timer = setTimeout(() => void this.refresh().catch(() => undefined), delay);
  }

  /** Forget the session locally (the device ID stays: it identifies this installation). */
  clear(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.accessTokenValue = null;
    this.expiresAt = 0;
    this.storage.remove(REFRESH_TOKEN);
    this.state.user = null;
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener({ ...this.state });
  }
}
