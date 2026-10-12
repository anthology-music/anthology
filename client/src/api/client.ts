import type { paths } from '@anthology/api-types';
import createClient from 'openapi-fetch';

import type { AuthSession } from '@/features/users/session';

/**
 * Typed REST client: adds the access token and retries once after refreshing it when
 * the server answers 401 (e.g. the token expired between check and request).
 */
export function createApi(
  session: AuthSession,
  options: { baseUrl?: string; fetch?: typeof fetch } = {},
) {
  const send = options.fetch ?? ((request: Request) => globalThis.fetch(request));

  async function authorized(request: Request): Promise<Response> {
    const token = await session.accessToken();
    const headers = new Headers(request.headers);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return send(new Request(request, { headers }));
  }

  return createClient<paths>({
    baseUrl: options.baseUrl ?? '',
    fetch: async (request: Request) => {
      const retry = request.clone();
      const response = await authorized(request);
      if (response.status !== 401 || !session.signedIn) return response;
      await session.refresh().catch(() => undefined);
      return session.signedIn ? authorized(retry) : response;
    },
  });
}

export type Api = ReturnType<typeof createApi>;
