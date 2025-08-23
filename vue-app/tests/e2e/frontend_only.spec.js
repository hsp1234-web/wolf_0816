import { test, expect } from '@playwright/test';
import path, { dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 此變數將用於儲存發送到 batch-tasks API 的請求內容
let batchTasksPayload = null;

test.beforeEach(async ({ page }) => {
  // 在每個測試開始前重置 payload
  batchTasksPayload = null;

  // 模擬 /api/stage-file 端點
  await page.route('**/api/stage-file', async (route) => {
    console.log('[Mock] 已攔截 /api/stage-file');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: "File staged successfully",
        file_id: `staged_${Date.now()}.txt`
      }),
    });
  });

  // 模擬 /api/batch-tasks 端點並捕獲請求內容
  await page.route('**/api/batch-tasks', async (route) => {
    console.log('[Mock] 已攔截 /api/batch-tasks');
    batchTasksPayload = route.request().postDataJSON();
    console.log('[Mock] 已捕獲的請求內容:', JSON.stringify(batchTasksPayload, null, 2));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: "Batch task accepted",
        batch_id: `batch_${Date.now()}`
      }),
    });
  });

  // 模擬其他可能用到的 API 端點以避免錯誤
  await page.route('**/api/youtube/validate_api_key', async route => {
      console.log('[Mock] 已攔截 /api/youtube/validate_api_key');
      await route.fulfill({ status: 200, json: { valid: true } });
  });
  await page.route('**/api/models/local', async route => {
      console.log('[Mock] 已攔截 /api/models/local');
      await route.fulfill({ status: 200, json: { "tiny": { "name": "tiny", "size": "75M" } } });
  });
});

test('Frontend Interaction and Command Assertion Test', async ({ page }) => {
  // 導航至 Vite 開發伺服器的 URL。
  // 注意：這假設開發伺服器正在 5173 埠上運行。
  await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded' });

  // 等待 Vue app 初始化完成
  await page.waitForFunction(() => window.vue_app, null, { timeout: 15000 });
  console.log('[Test] Vue app 已初始化。');

  // --- 步驟 1: 新增檔案轉錄任務 ---
  console.log('[Test] 新增檔案轉錄任務...');
  await page.click("button:has-text('本機檔案轉錄')");
  const filePath = path.join(__dirname, '../fixtures', 'test-audio.txt');
  await page.setInputFiles('input[type="file"]', filePath);
  await page.click("button:has-text('新增 1 個檔案至佇列')");
  console.log('[Test] 已將檔案任務新增至任務池。');

  // --- 步驟 2: 新增 YouTube 報告任務 ---
  console.log('[Test] 新增 YouTube 報告任務...');
  await page.click("button:has-text('YouTube 轉報告')");

  // 先輸入並儲存 API 金鑰來解鎖輸入框
  console.log('[Test] 輸入 API 金鑰...');
  // The input for the key is of type password
  await page.fill("input[type='password']", 'test-api-key');
  await page.click("button:has-text('儲存金鑰')");
  // My mock returns success, so I don't need to check for the "unverified" text
  await page.waitForSelector("text=金鑰已儲存");
  console.log('[Test] API 金鑰已儲存。');

  await page.fill("input[placeholder='YouTube 影片網址']", 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  await page.click("button:has-text('新增 1 個影片至佇列')");
  console.log('[Test] 已將 YouTube 任務新增至任務池。');

  // --- 步驟 3: 驗證任務池 UI ---
  console.log('[Test] 驗證任務池 UI...');
  const taskPool = page.locator(".card:has-text('任務佇列')");
  await expect(taskPool).toBeVisible();
  await expect(taskPool.locator('.task-item')).toHaveCount(2);
  console.log('[Test] 任務池中包含 2 個項目。');

  // --- 步驟 4: 在提交前截圖 ---
  const screenshotPath = 'frontend_interaction_test.png';
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(`[Test] 截圖已儲存至 ${screenshotPath}`);

  // --- 步驟 5: 提交任務並觸發 API 模擬 ---
  console.log('[Test] 提交任務池...');
  const submitButton = taskPool.locator("button:has-text('提交佇列中的 2 個任務')");
  await submitButton.click();

  // --- 步驟 6: 對捕獲的 payload 進行斷言 ---
  console.log('[Test] 對捕獲的 API payload 進行斷言...');
  expect(batchTasksPayload).not.toBeNull();

  // 斷言 1: 檢查根結構
  expect(batchTasksPayload).toHaveProperty('tasks');
  expect(Array.isArray(batchTasksPayload.tasks)).toBe(true);
  expect(batchTasksPayload.tasks).toHaveLength(2);

  // 斷言 2: 檢查第一個任務 (檔案轉錄)
  const fileTask = batchTasksPayload.tasks[0];
  expect(fileTask.type).toBe('transcription'); // 修正: 'transcription' 才對
  expect(fileTask.payload.file_id).toContain('staged_');
  expect(fileTask.payload.model).toBe('tiny'); // 假設 'tiny' 是預設模型

  // 斷言 3: 檢查第二個任務 (YouTube 報告)
  const youtubeTask = batchTasksPayload.tasks[1];
  expect(youtubeTask.type).toBe('youtube'); // 修正: type 是 'youtube'
  expect(youtubeTask.payload.url).toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  expect(youtubeTask.payload.tasks).toEqual(['summary', 'transcript']); // 驗證要求的子任務

  console.log('[Test] ✅ Payload 斷言通過！');

  // 最終檢查: 提交後任務池應被清空
  await expect(taskPool).not.toBeVisible();
  console.log('[Test] ✅ 提交後任務池已清空。');
});
