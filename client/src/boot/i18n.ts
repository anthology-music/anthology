import { defineBoot } from '#q-app';

import { createAppI18n } from '@/i18n/setup';

export default defineBoot(({ app }) => {
  app.use(createAppI18n());
});
