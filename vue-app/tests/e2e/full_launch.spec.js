// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Full Application E2E Test', () => {
  test('should launch the backend and render the frontend dashboard', async ({ page }) => {
    // The webServer in playwright.config.cjs should have already started the server.
    // We just need to navigate to the page.
    await page.goto('/');

    // 1. Check the page title to make sure we are on the right application
    await expect(page).toHaveTitle(/音訊轉錄儀/);

    // 2. Check for a key element on the dashboard to ensure the Vue app has mounted.
    // We use the health check button as it's a stable element with a data-testid.
    const healthCheckButton = page.getByTestId('health-check-button');
    await expect(healthCheckButton).toBeVisible();

    // 3. Check the text content of the button as an extra verification
    await expect(healthCheckButton).toHaveText('執行通訊測試');
  });
});
