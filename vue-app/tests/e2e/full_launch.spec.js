// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Full Application E2E Test', () => {
  test('should launch, respond to websocket, and render interactable UI', async ({ page }) => {
    // Promise to resolve when the correct websocket message is received
    const wsResponsePromise = new Promise((resolve, reject) => {
      page.on('websocket', ws => {
        ws.on('framereceived', event => {
          const data = JSON.parse(event.payload);
          // We are looking for the response to our specific request
          if (data.type === 'CHECK_LOCAL_MODELS_RESPONSE' && data.request_id) {
            console.log(`[Test] Received WebSocket response for CHECK_LOCAL_MODELS.`);
            resolve(data);
          }
        });
      });
    });

    // The webServer in playwright.config.cjs should have already started the server.
    // We just need to navigate to the page.
    await page.goto('/');

    // 1. Check the page title to make sure we are on the right application
    await expect(page).toHaveTitle(/音訊轉錄儀/);
    console.log('[Test] Page title is correct.');

    // 2. Wait for the WebSocket response with a specific timeout
    // This is the core of our fix verification.
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('WebSocket response for model check timed out after 5 seconds')), 5000)
    );
    await Promise.race([wsResponsePromise, timeoutPromise]);
    console.log('[Test] WebSocket response for model check received in time.');

    // 3. Check for a key element on the dashboard to ensure the Vue app has mounted.
    // We use the health check button as it's a stable element with a data-testid.
    const healthCheckButton = page.getByTestId('health-check-button');
    await expect(healthCheckButton).toBeVisible();
    console.log('[Test] Health check button is visible.');

    // 4. Most importantly, check that the button is enabled now that the app is not frozen.
    // This confirms the functional paralysis is gone.
    await expect(healthCheckButton).toBeEnabled();
    console.log('[Test] Health check button is enabled, UI is interactive.');

    // 5. Check the text content of the button as an extra verification
    await expect(healthCheckButton).toHaveText('執行通訊測試');
  });
});
