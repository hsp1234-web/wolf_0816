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
    // 步驟 1: 驗證本地檔案轉錄與模型下載
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 1: 驗證本地檔案轉錄與模型下載...');
    await page.click("button:has-text('本機檔案轉錄')");

    // 選擇 tiny 模型
    await page.selectOption('select#model-select', 'tiny');
    console.log('[JS Test] 已選擇 "tiny" 模型。');

    // 檢查模型是否需要下載
    const downloadButton = page.locator("button:has-text('下載模型')");
    const modelReadyButton = page.locator("button:has-text('模型已就緒')");

    if (await downloadButton.isVisible()) {
      console.log('[JS Test] 模型尚未下載，正在點擊下載按鈕...');
      await downloadButton.click();
      // 等待下載完成，按鈕變為「模型已就緒」
      await modelReadyButton.waitFor({ state: 'visible', timeout: 60000 }); // 增加超時以等待下載
      console.log('[JS Test] ✅ 模型下載成功並已就緒。');
    } else {
      console.log('[JS Test] 模型已存在，無需下載。');
    }

    // 現在模型已就緒，可以上傳檔案
    const filePath = path.join(__dirname, 'vue-app', 'tests', 'fixtures', 'test-audio.txt');
    await page.setInputFiles('input[type="file"]', filePath);
    console.log(`[JS Test] 已選擇測試檔案: ${filePath}`);

    // 驗證「新增至佇列」按鈕現在是啟用的
    console.log('[JS Test] 等待「新增至佇列」按鈕變為啟用狀態...');
    const addToQueueButton = page.locator("button:has-text('新增 1 個檔案至佇列')");
    await page.waitForFunction(
      (button) => !button.disabled,
      await addToQueueButton.elementHandle(),
      { timeout: 10000 }
    );
    console.log('[JS Test] ✅ 「新增至佇列」按鈕已啟用。');

    await addToQueueButton.click();
    console.log('[JS Test] ✅ 已點擊「新增至佇列」按鈕');

    // ----------------------------------------------------------------
    // 步驟 2: 驗證媒體下載器
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 2: 驗證媒體下載器...');
    await page.click("button:has-text('媒體下載器')");
    await page.fill("textarea[id='downloader-urls-input']", 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
    await page.click("button:has-text('開始下載')");

    // 驗證成功通知
    await page.waitForSelector("text=下載任務已成功建立！", { timeout: 5000 });
    console.log('[JS Test] ✅ 驗證成功: 下載器功能正常，未出現 t.startDownload 錯誤。');

    // ----------------------------------------------------------------
    // 步驟 3: 驗證 YouTube 報告與模型選擇
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 3: 驗證 YouTube 報告與模型選擇...');
    await page.click("button:has-text('YouTube 轉報告')");

    // 現在我們需要驗證真實的 API 呼叫流程
    // 注意：在測試環境中，我們假設後端 API 會返回一個模擬的成功回應
    await page.fill("input[type='password']", 'mock-valid-api-key');
    await page.click("button:has-text('儲存金鑰')");

    // 等待並驗證 API 呼叫後的正面狀態
    await page.waitForSelector("text=/金鑰有效/", { timeout: 10000 });
    console.log('[JS Test] ✅ 驗證成功: API 金鑰狀態已更新。');

    // 驗證模型下拉選單是否已填入內容
    const modelSelector = page.locator('select#gemini-model-select');
    const optionsCount = await modelSelector.locator('option').count();
    if (optionsCount <= 1) { // 應該要有一個以上的真實模型選項
      throw new Error(`模型下拉選單未成功載入。只找到 ${optionsCount} 個選項。`);
    }
    console.log(`[JS Test] ✅ 驗證成功: 模型下拉選單已載入 ${optionsCount} 個模型。`);

    await page.fill("input[placeholder='YouTube 影片網址']", 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
    await page.click("button:has-text('新增 1 個影片至佇列')");
    console.log('[JS Test] ✅ 已新增 YouTube 影片至佇列');


    // ----------------------------------------------------------------
    // 步驟 4: 驗證任務池
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 4: 驗證任務池...');
    const taskPool = page.locator(".card:has-text('任務佇列')");
    await taskPool.waitFor({ state: 'visible', timeout: 5000 });

    const tasksInPool = await taskPool.locator('.task-item').count();
    if (tasksInPool !== 2) {
      throw new Error(`預期任務池中有 2 個任務，但找到了 ${tasksInPool} 個`);
    }
    console.log(`[JS Test] ✅ 驗證成功: 任務池中顯示了 ${tasksInPool} 個任務。`);

    // ----------------------------------------------------------------
    // 步驟 5: 提交任務池 (預期會失敗，因為按鈕尚未對接)
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 5: 提交任務池...');
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
