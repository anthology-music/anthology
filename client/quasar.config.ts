// Quasar CLI configuration: https://v2.quasar.dev/quasar-cli-vite/quasar-config-file
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '#q-app';

// The design tokens are the single source of the colours (docs/design/README.md).
const tokens = readFileSync(
  fileURLToPath(new URL('../docs/design/tokens.css', import.meta.url)),
  'utf8',
);

function token(name: string): string {
  const match = tokens.match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!match?.[1]) throw new Error(`design token --${name} not found`);
  return match[1].trim();
}

export default defineConfig(() => ({
  boot: ['i18n', 'auth'],
  css: ['app.css'],
  extras: ['material-icons'],
  build: {
    target: { browser: ['es2022', 'firefox115', 'chrome115', 'safari16'] },
    typescript: { strict: true, vueShim: true },
    vueRouterMode: 'history',
  },
  devServer: {
    open: false,
    // The Python server (uvicorn on port 8400) serves REST and the WebSocket.
    proxy: {
      '/api': { target: 'http://localhost:8400', ws: true },
    },
  },
  framework: {
    config: {
      dark: true,
      brand: {
        primary: token('color-accent'),
        secondary: token('color-accent-strong'),
        accent: token('color-accent'),
        dark: token('color-bg'),
        'dark-page': token('color-bg'),
        positive: token('color-status-ok'),
        negative: token('color-status-error'),
        info: token('color-status-running'),
        warning: token('color-status-warning'),
      },
    },
    plugins: [],
  },
  animations: [],
}));
