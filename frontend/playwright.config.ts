import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end configuration.
 *
 * The browser talks to the real FastAPI backend, which is started in demo mode
 * with the committed Woodbury, Minnesota sample graph (see config/areas.yaml).
 * The database is a throwaway file in the system temp folder so the tests never
 * touch the development database. If a dev server is already running,
 * `reuseExistingServer` keeps it instead of starting a second copy.
 *
 * `npm run e2e` requires Chromium (`npm run e2e:install` once).
 */
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } },
    },
  ],
  webServer: [
    {
      // Demo mode + a fresh temporary SQLite database for every run.
      command: 'node e2e/start-backend.mjs',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
