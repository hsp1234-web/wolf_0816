// @ts-check
import { test, expect } from '@playwright/test';

test('Main page should load and have the correct title', async ({ page }) => {
  await page.goto('http://localhost:5173');
  await expect(page).toHaveTitle(/音訊轉錄儀/);
});
