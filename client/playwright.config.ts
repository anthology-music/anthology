import { defineConfig, devices } from '@playwright/test';

const serverPort = process.env.ANTHOLOGY_E2E_SERVER_PORT ?? '8490';
const clientPort = process.env.ANTHOLOGY_E2E_CLIENT_PORT ?? '9090';

/**
 * End-to-end tests against the real server and PostgreSQL.
 * Needs ANTHOLOGY_E2E_DATABASE_URL (a database dedicated to tests) and uv.
 */
export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  timeout: 60_000,
  use: {
    baseURL: `http://localhost:${clientPort}`,
    locale: 'de-CH',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: './e2e/start-server.sh',
      url: `http://localhost:${serverPort}/api/v1/ready`,
      env: { ANTHOLOGY_E2E_SERVER_PORT: serverPort },
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: 'pipe',
    },
    {
      command: `pnpm exec quasar dev --port ${clientPort}`,
      url: `http://localhost:${clientPort}`,
      env: { ANTHOLOGY_API_URL: `http://localhost:${serverPort}` },
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
