import { defineConfig, devices } from '@playwright/test';
import path from 'path';

const port = process.env.PORT || 5173;
const baseURL = `http://localhost:${port}`;

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/frontend_only.spec.js', // <<<<<<<<<<< 已將測試目標換回正式測試檔案
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  timeout: 60 * 1000,
  use: {
    baseURL: baseURL,
    trace: 'on',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'bun run dev',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    stdout: 'pipe',
    stderr: 'pipe',
    timeout: 120 * 1000,
    cwd: path.resolve(__dirname),
  },
});
