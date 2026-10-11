import { describe, expect, it } from 'vitest';

import messages from '@/i18n';

function keys(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object') return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    keys(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe('i18n', () => {
  it('has the same keys in German and English', () => {
    expect(keys(messages.en).sort()).toEqual(keys(messages.de).sort());
  });

  it('has no empty texts', () => {
    for (const locale of [messages.de, messages.en]) {
      const empty = keys(locale).filter((path) => {
        const text = path
          .split('.')
          .reduce<unknown>((node, key) => (node as Record<string, unknown>)[key], locale);
        return typeof text !== 'string' || text.trim() === '';
      });
      expect(empty).toEqual([]);
    }
  });
});
