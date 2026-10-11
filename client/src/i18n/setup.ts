import { createI18n } from 'vue-i18n';

import messages, { defaultLocale, fallbackLocale } from './index';

export type MessageLanguages = keyof typeof messages;
export type MessageSchema = (typeof messages)['de'];

/* eslint-disable @typescript-eslint/no-empty-object-type */
declare module 'vue-i18n' {
  export interface DefineLocaleMessage extends MessageSchema {}
  export interface DefineDateTimeFormat {}
  export interface DefineNumberFormat {}
}
/* eslint-enable @typescript-eslint/no-empty-object-type */

export function createAppI18n(locale: MessageLanguages = defaultLocale) {
  return createI18n<{ message: MessageSchema }, MessageLanguages>({
    locale,
    fallbackLocale,
    legacy: false,
    messages,
  });
}
