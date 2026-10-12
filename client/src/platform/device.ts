import type { Schemas } from '@anthology/api-types';

/** Describes this client installation for device registration on sign-in. */
export function describeDevice(): Omit<Schemas['DeviceIn'], 'id'> {
  const agent = globalThis.navigator?.userAgent ?? '';
  const browser = /Firefox\//.test(agent)
    ? 'Firefox'
    : /Edg\//.test(agent)
      ? 'Edge'
      : /Chrome\//.test(agent)
        ? 'Chrome'
        : /Safari\//.test(agent)
          ? 'Safari'
          : 'Browser';
  const system = /Android/.test(agent)
    ? 'Android'
    : /iPhone|iPad/.test(agent)
      ? 'iOS'
      : /Mac OS X/.test(agent)
        ? 'macOS'
        : /Windows/.test(agent)
          ? 'Windows'
          : /Linux/.test(agent)
            ? 'Linux'
            : '';
  return {
    name: system ? `${browser} · ${system}` : browser,
    type: 'web',
    platform: agent.slice(0, 128),
  };
}
