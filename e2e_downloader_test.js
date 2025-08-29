const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    console.log('Navigating to http://localhost:8000...');
    await page.goto('http://localhost:8000', { waitUntil: 'networkidle' });

    console.log('Clicking on the Media Downloader tab...');
    await page.click('button[data-tab="downloader-tab"]');

    const downloaderTabContent = await page.waitForSelector('#downloader-tab.active', { timeout: 5000 });
    if (!downloaderTabContent) {
        throw new Error('Downloader tab content did not become active.');
    }
    console.log('Downloader tab is active.');

    console.log('Typing mock URL...');
    await page.fill('#downloader-urls-input', 'USE_MOCK_DOWNLOAD');

    console.log('Clicking the download button...');
    await page.click('#start-download-btn');

    console.log('Waiting for the download task to complete...');
    // Wait for the task item to appear and its status to show '✅ 完成'
    await page.waitForSelector('#downloader-tasks .task-item .task-status:has-text("✅ 完成")', { timeout: 60000 });

    console.log('Download task completed successfully.');

    console.log('Taking screenshot...');
    await page.screenshot({ path: '/app/downloader_test_result.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Screenshot saved as /app/downloader_test_result.jpg');

  } catch (error) {
    console.error('Error during Playwright execution:', error);
    // On error, take a screenshot for debugging
    await page.screenshot({ path: '/app/downloader_test_error.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Error screenshot saved as /app/downloader_test_error.jpg');
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
