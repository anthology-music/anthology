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
