import { defineConfig, devices } from '@playwright/test';

const serverPort = process.env.ANTHOLOGY_E2E_SERVER_PORT ?? '8490';
const clientPort = process.env.ANTHOLOGY_E2E_CLIENT_PORT ?? '9090';

/**
 * The walkthrough that takes the manual's screenshots (ADR 0023) against the end-to-end server:
 * a fresh database with a generated library, the fake source service and the fake Raumfeld host
 * (client/e2e/start-server.sh). Needs ANTHOLOGY_E2E_DATABASE_URL and uv, like the end-to-end tests.
 */
export default defineConfig({
  testDir: '.',
  testMatch: 'walkthrough.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  timeout: 180_000,
  use: {
    baseURL: `http://localhost:${clientPort}`,
    viewport: { width: 1280, height: 800 },
    colorScheme: 'dark',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: [
    {
      command: '../../client/e2e/start-server.sh',
      url: `http://localhost:${serverPort}/api/v1/ready`,
      env: { ANTHOLOGY_E2E_SERVER_PORT: serverPort, ANTHOLOGY_E2E_SERVE_DEMO: 'false' },
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: 'pipe',
    },
    {
      command: `pnpm --dir ../../client exec quasar dev --port ${clientPort}`,
      url: `http://localhost:${clientPort}`,
      env: { ANTHOLOGY_API_URL: `http://localhost:${serverPort}` },
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
