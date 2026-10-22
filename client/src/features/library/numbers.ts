import { useI18n } from 'vue-i18n';

/** Counts in the reader's locale (`38.905`), plural texts with the formatted number. */
export function useCounts() {
  const { t, locale } = useI18n();
  const number = (value: number | null | undefined) =>
    value === null || value === undefined ? '…' : new Intl.NumberFormat(locale.value).format(value);
  const count = (key: string, value: number) =>
    t(`library.count.${key}`, { n: number(value) }, value);
  return { number, count };
}

const SIZE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte', 'terabyte'] as const;

/** A size in bytes with decimal units in the reader's locale (`40 GB`, `1,5 TB`). */
export function formatSize(bytes: number, locale: string): string {
  let unit = 0;
  let amount = bytes;
  while (amount >= 1000 && unit < SIZE_UNITS.length - 1) {
    amount /= 1000;
    unit += 1;
  }
  return new Intl.NumberFormat(locale, {
    style: 'unit',
    unit: SIZE_UNITS[unit],
    unitDisplay: 'short',
    maximumFractionDigits: unit === 0 ? 0 : 1,
  }).format(amount);
}
