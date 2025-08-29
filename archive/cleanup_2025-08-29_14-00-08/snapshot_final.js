const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    console.log('Navigating to http://localhost:8000...');
    await page.goto('http://localhost:8000', { waitUntil: 'networkidle' });
    console.log('Page loaded. Taking screenshot...');
    await page.screenshot({ path: '/app/final_frontend.jpg', type: 'jpeg', quality: 90, fullPage: true });
    console.log('Screenshot saved as /app/final_frontend.jpg');
  } catch (error) {
    console.error('Error during Playwright execution:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
