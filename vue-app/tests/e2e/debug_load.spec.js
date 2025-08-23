import { test, expect } from '@playwright/test';

test('Debug Page Load Test', async ({ page }) => {
  console.log('[Debug Test] 開始執行單純載入頁面測試...');

  // 監聽所有瀏覽器端的 console 訊息並印出
  page.on('console', msg => {
    console.log(`[Browser Console] ${msg.type()}: ${msg.text()}`);
  });

  // 監聽頁面錯誤
  page.on('pageerror', error => {
    console.error(`[Browser Page Error] ${error.message}`);
  });

  try {
    // 步驟 1: 導航至頁面
    console.log('[Debug Test] 導航至 http://localhost:5173 ...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('[Debug Test] 頁面導航完成。');

    // 步驟 2: 檢查頁面標題
    const title = await page.title();
    console.log(`[Debug Test] 頁面標題為: "${title}"`);
    expect(title).not.toBe('');

    // 步驟 3: 等待一段時間，觀察是否有錯誤發生
    console.log('[Debug Test] 等待 10 秒鐘...');
    await page.waitForTimeout(10000);
    console.log('[Debug Test] 等待結束。');

    console.log('[Debug Test] ✅ 單純載入頁面測試成功！');
  } catch (e) {
    console.error('[Debug Test] 執行測試時發生錯誤:', e);
    // 擷取失敗畫面
    await page.screenshot({ path: 'debug-failure.png' });
    console.log('[Debug Test] 已擷取失敗畫面至 debug-failure.png');
    throw e; // 重新拋出錯誤以標記測試失敗
  }
});
