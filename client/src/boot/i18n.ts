import { defineBoot } from '#q-app';

import { storedLanguage } from '@/i18n/language';
import { createAppI18n } from '@/i18n/setup';

export default defineBoot(({ app }) => {
  app.use(createAppI18n(storedLanguage()));
  document.documentElement.lang = storedLanguage();
});
