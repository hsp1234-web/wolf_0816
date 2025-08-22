// run_browser_test.js
// 這是一個獨立的 Node.js 腳本，使用 Playwright 函式庫來執行瀏覽器測試。
// 它不依賴 Playwright 的測試運行器，因此可以避免複雜的設定問題。

const { chromium } = require('playwright');

(async () => {
  // 從命令列參數獲取目標 URL，如果未提供，則使用預設值。
  // 這讓我們的腳本更有彈性。
  const url = process.argv[2] || 'http://127.0.0.1:8008';
  console.log(`[JS Test] 準備在 ${url} 上執行瀏覽器驗證...`);

  let browser;
  let context;
  let page;
  try {
    // 啟動瀏覽器
    browser = await chromium.launch(); // 回到預設的無頭模式
    context = await browser.newContext();

    // 啟用追蹤
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });

    page = await context.newPage();

    // 監聽並印出所有瀏覽器端的 console 訊息
    page.on('console', msg => console.log(`[Browser Console] ${msg.type()}: ${msg.text()}`));
    page.on('pageerror', error => console.log(`[Browser Page Error] ${error.message}`));

    console.log(`[JS Test] 導航至: ${url}`);
    // 前往目標頁面，等待 DOM 內容載入完成
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });

    // 等待 Vue app 將自身實例附加到 window 物件上
    console.log('[JS Test] 等待 Vue app 初始化...');
    await page.waitForFunction(() => window.vue_app, null, { timeout: 10000 });
    console.log('[JS Test] ✅ Vue app 已找到！');

    // 手動觸發 WebSocket 初始化，以繞過在測試環境中 onMounted 可能不被觸發的問題
    await page.evaluate(() => {
      if (window.vue_app) {
        const pinia = window.vue_app.config.globalProperties.$pinia;
        const tasksStore = pinia._s.get('tasks'); // 使用 store 的 ID 'tasks' 來獲取實例
        if (tasksStore) {
          console.log('[Test Evaluate] 正在手動觸發 WebSocket 初始化...');
          tasksStore.initializeSystem();
        } else {
          console.error('[Test Evaluate] 錯誤: 找不到 "tasks" store！');
        }
      } else {
        console.error('[Test Evaluate] 錯誤: 找不到 window.vue_app 實例！');
      }
    });

    console.log('[JS Test] 正在驗證初始 UI 狀態...');

    // 定位包含「進行中任務」標題的卡片
    const pendingTasksCard = page.locator(".card:has-text('進行中任務')");
    // 在該卡片內定位「暫無執行中任務」的文字
    const noTasksMessage = pendingTasksCard.locator('text=暫無執行中任務');

    // 等待目標元素在指定的超時時間內變得可見
    await noTasksMessage.waitFor({ state: 'visible', timeout: 15000 });

    console.log('[JS Test] ✅ 驗證成功: 「暫無執行中任務」訊息已正確顯示。');

    // 測試成功，關閉瀏覽器並以狀態碼 0 退出
    await browser.close();
    process.exit(0);

  } catch (error) {
    // 如果在 try 區塊中發生任何錯誤（例如，元素找不到或超時）
    console.error('[JS Test] ❌ 測試失敗:', error.message);
    if (browser) {
      const tracePath = 'trace.zip';
      // 停止追蹤並將結果儲存到檔案中
      await context.tracing.stop({ path: tracePath });
      console.log(`[JS Test] 偵錯追蹤檔案已儲存至: ${tracePath}`);

      const screenshotPath = 'test-failure.png';
      await page.screenshot({ path: screenshotPath });
      console.log(`[JS Test] 已擷取失敗畫面至: ${screenshotPath}`);

      await browser.close();
    }
    // 測試失敗，以狀態碼 1 退出
    process.exit(1);
  }
})();
