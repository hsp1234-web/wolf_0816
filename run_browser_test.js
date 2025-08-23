const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8008';
  console.log(`[JS Test] 準備在 ${url} 上執行新的 E2E 測試...`);

  let browser;
  let context;
  let page;
  try {
    browser = await chromium.launch({ headless: true }); // 在無頭模式下運行
    context = await browser.newContext();
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    page = await context.newPage();

    page.on('console', msg => console.log(`[Browser Console] ${msg.text()}`));
    page.on('pageerror', error => console.error(`[Browser Page Error] ${error.message}`));

    console.log(`[JS Test] 導航至: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });

    console.log('[JS Test] 等待 Vue app 初始化...');
    await page.waitForFunction(() => window.vue_app, null, { timeout: 15000 });
    console.log('[JS Test] ✅ Vue app 已找到！');

    // ----------------------------------------------------------------
    // 步驟 1: 新增檔案轉錄任務
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 1: 新增檔案轉錄任務...');
    await page.click("button:has-text('本機檔案轉錄')");

    const filePath = path.join(__dirname, 'vue-app', 'tests', 'fixtures', 'test-audio.txt');
    await page.setInputFiles('input[type="file"]', filePath);
    console.log(`[JS Test] 已選擇測試檔案: ${filePath}`);

    await page.click("button:has-text('新增 1 個檔案至佇列')");
    console.log('[JS Test] ✅ 已點擊「新增至佇列」按鈕');

    // ----------------------------------------------------------------
    // 步驟 2: 新增 YouTube 報告任務
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 2: 新增 YouTube 報告任務...');
    await page.click("button:has-text('YouTube 轉報告')");

    // 由於我們註解掉了驗證邏輯，現在只需輸入即可
    await page.fill("input[type='password']", 'test-api-key');
    await page.click("button:has-text('儲存金鑰')");
    await page.waitForSelector("text=金鑰已儲存 (未驗證)");
    console.log('[JS Test] 已輸入並儲存 API 金鑰');

    await page.fill("input[placeholder='YouTube 影片網址']", 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
    await page.click("button:has-text('新增 1 個影片至佇列')");
    console.log('[JS Test] ✅ 已新增 YouTube 影片至佇列');

    // ----------------------------------------------------------------
    // 步驟 3: 驗證任務池
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 3: 驗證任務池...');
    const taskPool = page.locator(".card:has-text('任務佇列')");
    await taskPool.waitFor({ state: 'visible', timeout: 5000 });

    const tasksInPool = await taskPool.locator('.task-item').count();
    if (tasksInPool !== 2) {
      throw new Error(`預期任務池中有 2 個任務，但找到了 ${tasksInPool} 個`);
    }
    console.log(`[JS Test] ✅ 驗證成功: 任務池中顯示了 ${tasksInPool} 個任務。`);

    // ----------------------------------------------------------------
    // 步驟 4: 提交任務池 (預期會失敗，因為按鈕尚未對接)
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 4: 提交任務池...');
    const submitButton = taskPool.locator("button:has-text('提交佇列中的 2 個任務')");
    await submitButton.click();
    console.log('[JS Test] 已點擊「提交佇列」按鈕。');

    // ----------------------------------------------------------------
    // 步驟 5: 驗證結果
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 5: 驗證結果...');

    // 驗證任務池是否已清空
    await taskPool.waitFor({ state: 'hidden', timeout: 5000 });
    console.log('[JS Test] ✅ 驗證成功: 任務池已清空。');

    // 驗證任務是否已出現在「進行中任務」列表
    const pendingTasksList = page.locator(".card:has-text('進行中任務')");
    await pendingTasksList.waitFor({ state: 'visible', timeout: 5000 });

    // 等待，直到進行中任務列表包含兩個新任務
    await page.waitForFunction(() => {
        const pendingTasksNode = document.querySelector(".card:has-text('進行中任務')");
        if (!pendingTasksNode) return false;
        const taskItems = pendingTasksNode.querySelectorAll('.task-item');
        return taskItems.length >= 2;
    }, null, { timeout: 15000 });

    const tasksInPending = await pendingTasksList.locator('.task-item').count();
    if (tasksInPending < 2) {
        throw new Error(`預期「進行中任務」列表中至少有 2 個任務，但只找到 ${tasksInPending} 個`);
    }
    console.log(`[JS Test] ✅ 驗證成功: 「進行中任務」列表中出現了 ${tasksInPending} 個任務。`);

    console.log('[JS Test] 🎉 E2E 測試全部通過！');
    await browser.close();
    process.exit(0);

  } catch (error) {
    console.error('[JS Test] ❌ 測試失敗:', error.message);
    if (context) {
      const tracePath = 'trace.zip';
      await context.tracing.stop({ path: tracePath });
      console.log(`[JS Test] 偵錯追蹤檔案已儲存至: ${tracePath}`);
    }
    if (page) {
      const screenshotPath = 'test-failure.png';
      await page.screenshot({ path: screenshotPath });
      console.log(`[JS Test] 已擷取失敗畫面至: ${screenshotPath}`);
    }
    if (browser) {
      await browser.close();
    }
    process.exit(1);
  }
})();
