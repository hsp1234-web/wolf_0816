import { defineConfig, devices } from '@playwright/test';
import path from 'path';

// The backend server will run on port 8000
const baseURL = `http://localhost:8000`;

export default defineConfig({
  testDir: './tests/e2e',
  // Point to the new full_launch test file
  testMatch: '**/full_launch.spec.js',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  // User requested 120 second timeout
  timeout: 120 * 1000,
  use: {
    baseURL: baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Configure the web server to run the actual backend
  webServer: {
    // Command to start the backend service manager
    command: 'python scripts/run_services.py',
    // URL for Playwright to poll to check if the server is ready.
    // Using the health check endpoint is the most reliable way.
    url: `${baseURL}/api/health`,
    reuseExistingServer: !process.env.CI,
    stdout: 'pipe',
    stderr: 'pipe',
    // Timeout for the web server to start
    timeout: 120 * 1000,
    // The CWD is the project root, not the vue-app directory
    cwd: path.resolve(__dirname, '..'),
    // Set environment variables for the test server
    env: {
      E2E_TESTING: '1',
    },
  },
});
