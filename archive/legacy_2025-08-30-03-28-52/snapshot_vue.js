const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    console.log('Navigating to http://localhost:5173/ui/...');
    await page.goto('http://localhost:5173/ui/', { waitUntil: 'networkidle' });
    console.log('Page loaded. Taking screenshot...');
    await page.screenshot({ path: 'refactored_frontend.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Screenshot saved as refactored_frontend.jpg');
  } catch (error) {
    console.error('Error during Playwright execution:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
