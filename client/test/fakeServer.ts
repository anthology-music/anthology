/** A scripted HTTP server for tests: routes by "METHOD /path" to handlers. */
export type Handler = (request: Request) => Response | Promise<Response>;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export function fakeFetch(routes: Record<string, Handler>) {
  const calls: string[] = [];
  const fetch = async (input: Request): Promise<Response> => {
    const url = new URL(input.url);
    const route = `${input.method} ${url.pathname}`;
    calls.push(route);
    const handler = routes[route];
    if (!handler) return json({ detail: 'not_found' }, 404);
    return handler(input);
  };
  return { fetch: fetch as typeof globalThis.fetch, calls };
}

let counter = 0;

export function tokens(
  overrides: Partial<{ expiresInMs: number; role: string; username: string }> = {},
) {
  counter += 1;
  const { expiresInMs = 15 * 60_000, role = 'admin', username = 'admin' } = overrides;
  return {
    access_token: `access-${counter}`,
    refresh_token: `device-1.refresh-${counter}`,
    token_type: 'bearer',
    expires_at: new Date(Date.now() + expiresInMs).toISOString(),
    device_id: 'device-1',
    user: {
      id: 'user-1',
      username,
      display_name: 'Admin',
      role,
      origin: 'local',
      active: true,
      created_at: new Date().toISOString(),
    },
  };
}
