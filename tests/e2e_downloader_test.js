const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    console.log('Navigating to http://localhost:8000...');
    await page.goto('http://localhost:8000', { waitUntil: 'networkidle' });

    console.log('Clicking on the Media Downloader tab...');
    await page.click('button[data-tab="downloader-tab"]');
    await page.waitForSelector('#downloader-tab.active', { timeout: 5000 });
    console.log('Downloader tab is active.');

    console.log('Typing mock URL...');
    await page.fill('#downloader-urls-input', 'USE_MOCK_DOWNLOAD');

    console.log('Clicking the download button...');
    await page.click('#start-download-btn');

    console.log('Waiting for the download task to complete and buttons to appear...');
    const previewBtn = await page.waitForSelector('[data-testid="preview-btn"]', { timeout: 10000 });
    const sendToReportBtn = await page.waitForSelector('[data-testid="send-to-report-btn"]', { timeout: 10000 });

    if (!previewBtn || !sendToReportBtn) {
        throw new Error('Action buttons did not appear after download.');
    }
    console.log('Download task completed and action buttons are visible.');

    console.log('Taking Screenshot 1: Completed task with buttons...');
    await page.screenshot({ path: '/app/screenshot_1_buttons.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Screenshot 1 saved.');

    console.log('Clicking Preview button...');
    await previewBtn.click();
    await page.waitForSelector('#preview-modal[style*="display: flex"]', { timeout: 5000 });
    console.log('Preview modal is visible.');

    console.log('Taking Screenshot 2: Preview modal...');
    await page.screenshot({ path: '/app/screenshot_2_preview.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Screenshot 2 saved.');

    console.log('Closing preview modal...');
    await page.click('#modal-close-btn');
    await page.waitForSelector('#preview-modal', { state: 'hidden', timeout: 5000 });
    console.log('Preview modal closed.');

    console.log('Clicking Send to Report button...');
    await sendToReportBtn.click();
    await page.waitForSelector('#youtube-report-tab.active', { timeout: 5000 });
    const urlInputValue = await page.inputValue('#youtube-url');
    if (!urlInputValue.includes('mock.m4a')) {
        throw new Error(`Report URL input has wrong value: ${urlInputValue}`);
    }
    console.log('Report tab is active and input is populated.');

    console.log('Taking Screenshot 3: Sent to report tab...');
    await page.screenshot({ path: '/app/screenshot_3_report_tab.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Screenshot 3 saved.');

    console.log('E2E test fully passed!');

  } catch (error) {
    console.error('Error during Playwright execution:', error);
    await page.screenshot({ path: '/app/downloader_test_error.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Error screenshot saved as /app/downloader_test_error.jpg');
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
