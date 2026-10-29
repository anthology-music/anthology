import { browserStorage } from '@/platform/storage';

import messages, { defaultLocale } from './index';

export type Language = keyof typeof messages;
export const LANGUAGES = Object.keys(messages) as Language[];
const KEY = 'anthology.language';

/** The interface language chosen on this device (Settings), else German (the first language). */
export function storedLanguage(): Language {
  const value = browserStorage.get(KEY);
  return value && (LANGUAGES as string[]).includes(value) ? (value as Language) : defaultLocale;
}

export function storeLanguage(language: Language): void {
  browserStorage.set(KEY, language);
}
