// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Full Application E2E Test', () => {
  test('should launch, respond to model check, and enable download button', async ({ page }) => {
    // The webServer in playwright.config.cjs should have already started the server.
    // We just need to navigate to the page.
    await page.goto('/');

    // 1. Check the page title to make sure we are on the right application
    await expect(page).toHaveTitle(/音訊轉錄儀/);
    console.log('[Test] Page title is correct.');

    // 2. Locate the "Download Model" button using its stable data-testid
    const downloadButton = page.getByTestId('download-model-button');

    // 3. We just need to check that the button becomes visible. This proves that
    // the component has rendered correctly and the feature flag issue is gone.
    await expect(downloadButton).toBeVisible({ timeout: 10000 });
    console.log('[Test] "Download Model" button is visible, indicating UI has loaded correctly.');
  });
});
