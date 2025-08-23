const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8008';
  console.log(`[JS Test] 準備在 ${url} 上執行新的 E2E 驗證測試...`);

  let browser;
  let context;
  let page;
  try {
    browser = await chromium.launch({ headless: true }); // 在無頭模式下運行
    context = await browser.newContext();
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    page = await context.newPage();

    page.on('console', msg => {
        // 忽略來自 antdv 的無關警告
        if (msg.text().includes('is not a valid value for custom-string')) return;
        console.log(`[Browser Console] ${msg.text()}`);
    });
    page.on('pageerror', error => console.error(`[Browser Page Error] ${error.message}`));

    console.log(`[JS Test] 導航至: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });

    console.log('[JS Test] 等待 Vue app 初始化...');
    await page.waitForFunction(() => window.vue_app, null, { timeout: 15000 });
    console.log('[JS Test] ✅ Vue app 已找到！');

    // ----------------------------------------------------------------
    // 步驟 1: 驗證儀表板和工作者狀態 UI
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 1: 驗證儀表板和工作者狀態 UI...');
    await page.waitForSelector("text=狀態: 準備就緒", { timeout: 10000 });
    console.log('[JS Test] ✅ 驗證成功: 全域儀表板顯示「準備就緒」。');
    await page.waitForSelector("h2:has-text('工作者狀態')", { timeout: 5000 });
    console.log('[JS Test] ✅ 驗證成功: 工作者狀態面板已呈現。');

    // 等待至少一個工作者狀態出現，表示後端通訊正常
    const workerStatusCard = page.locator(".card:has-text('工作者狀態')");
    await workerStatusCard.locator('text=transcription').waitFor({ state: 'visible', timeout: 15000 });
    console.log('[JS Test] ✅ 驗證成功: 至少一個工作者的狀態已顯示。');


    // ----------------------------------------------------------------
    // 步驟 2: 驗證本地檔案轉錄流程
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 2: 驗證本地檔案轉錄...');
    await page.click("button:has-text('本機檔案轉錄')");

    // 選擇 tiny 模型並設定 beam size
    await page.selectOption('select#model-select', 'tiny');
    console.log('[JS Test] 已選擇 "tiny" 模型。');
    await page.fill('input#beam-size-input', '1');
    console.log('[JS Test] 已設定光束大小為 1。');

    // 檢查模型是否需要下載
    const downloadButton = page.locator("button:has-text('下載模型')");
    const modelReadyButton = page.locator("button:has-text('模型已就緒')");

    if (await downloadButton.isVisible()) {
      console.log('[JS Test] 模型尚未下載，正在點擊下載按鈕...');
      await downloadButton.click();
      await modelReadyButton.waitFor({ state: 'visible', timeout: 90000 }); // 增加超時以等待下載
      console.log('[JS Test] ✅ 模型下載成功並已就緒。');
    } else {
      console.log('[JS Test] 模型已存在，無需下載。');
    }

    // 上傳檔案
    const filePath = path.join(__dirname, 'vue-app', 'tests', 'fixtures', 'test-audio.txt');
    await page.setInputFiles('input[type="file"]', filePath);
    console.log(`[JS Test] 已選擇測試檔案: ${filePath}`);

    // 新增至佇列
    const addToQueueButton = page.locator("button:has-text('新增 1 個檔案至佇列')");
    await addToQueueButton.click();
    console.log('[JS Test] ✅ 已點擊「新增至佇列」按鈕');

    // ----------------------------------------------------------------
    // 步驟 3: 提交任務並等待結果
    // ----------------------------------------------------------------
    console.log('[JS Test] 步驟 3: 提交任務並等待結果...');
    const taskPool = page.locator(".card:has-text('任務佇列')");
    await taskPool.waitFor({ state: 'visible', timeout: 5000 });

    const submitButton = taskPool.locator("button:has-text('提交佇列中的 1 個任務')");
    await submitButton.click();
    console.log('[JS Test] 已點擊「提交佇列」按鈕。');

    // 等待任務出現在「已完成任務」列表
    console.log('[JS Test] 等待任務完成...');
    const completedTasksList = page.locator(".card:has-text('已完成任務')");
    await completedTasksList.waitFor({ state: 'visible', timeout: 5000 });

    // 等待包含原始檔名的任務項目出現，並且狀態為 'completed'
    const completedTaskLocator = completedTasksList.locator(`.task-item:has-text('test-audio.txt')`);
    await completedTaskLocator.waitFor({ state: 'visible', timeout: 120000 }); // 增加超時以等待轉錄完成

    const taskStatus = await completedTaskLocator.locator('.task-status-badge.status-completed').innerText();
    if (taskStatus.trim().toLowerCase() !== 'completed') {
        throw new Error(`預期任務狀態為 'completed'，但得到 '${taskStatus}'`);
    }
    console.log('[JS Test] ✅ 驗證成功: 轉錄任務已完成！');

    // 點擊預覽按鈕
    await completedTaskLocator.locator("button:has-text('預覽')").click();

    // 驗證預覽 Modal 是否出現
    const previewModal = page.locator(".preview-modal");
    await previewModal.waitFor({ state: 'visible', timeout: 5000 });

    // 驗證 Modal 中是否包含轉錄結果的文字
    // 因為是模擬音訊，我們只檢查是否有任何輸出即可
    const transcriptContent = await previewModal.locator('pre').innerText();
    if (transcriptContent.length < 5) {
        throw new Error('預覽 Modal 中的轉錄結果為空或過短。');
    }
    console.log('[JS Test] ✅ 驗證成功: 預覽 Modal 已顯示且包含轉錄內容。');


    console.log('[JS Test] 🎉 E2E 驗證測試全部通過！');
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
