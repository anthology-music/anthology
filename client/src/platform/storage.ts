/**
 * Small key-value storage interface. The web app uses localStorage; native shells
 * (milestone 3) can provide secure storage behind the same interface.
 */
export interface KeyValueStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
  remove(key: string): void;
}

export const browserStorage: KeyValueStorage = {
  get: (key) => globalThis.localStorage?.getItem(key) ?? null,
  set: (key, value) => globalThis.localStorage?.setItem(key, value),
  remove: (key) => globalThis.localStorage?.removeItem(key),
};

export function memoryStorage(initial: Record<string, string> = {}): KeyValueStorage {
  const values = new Map(Object.entries(initial));
  return {
    get: (key) => values.get(key) ?? null,
    set: (key, value) => void values.set(key, value),
    remove: (key) => void values.delete(key),
  };
}
