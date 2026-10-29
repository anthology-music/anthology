import DefaultTheme from 'vitepress/theme';
import { h } from 'vue';

import Screenshot from './Screenshot.vue';
import UnreleasedNotice from './UnreleasedNotice.vue';
import VersionSelector from './VersionSelector.vue';

export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'doc-before': () => h(UnreleasedNotice),
      'nav-bar-content-after': () => h(VersionSelector),
    }),
  enhanceApp({ app }: { app: import('vue').App }) {
    app.component('Screenshot', Screenshot);
  },
};
