// @ts-check
import { test, expect } from '@playwright/test';

test('User should be able to select a file for upload', async ({ page }) => {
  // 導覽至主頁面
  await page.goto('http://localhost:5173');

  // 找到隱藏的檔案輸入元素
  const fileInput = page.locator('#file-input-trigger');

  // 準備要上傳的檔案路徑 (相對於專案根目錄)
  const filePath = 'tests/fixtures/test-audio.txt';

  // 模擬使用者選擇檔案
  await fileInput.setInputFiles(filePath);

  // 驗證檔案是否出現在待處理列表中
  const fileList = page.locator('#file-list');
  await expect(fileList).toContainText('test-audio.txt');
});
