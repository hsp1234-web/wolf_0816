import { chromium } from 'playwright';
import http from 'http';
import serveStatic from 'serve-static';
import finalhandler from 'finalhandler';

const PORT = 42649;
const STATIC_DIR = 'src/static';
const TARGET_URL = `http://127.0.0.1:${PORT}/mp3.html`;
const EXPECTED_TITLE = '音訊轉錄儀';

async function main() {
    // 1. 啟動靜態檔案伺服器
    const serve = serveStatic(STATIC_DIR, { index: ['mp3.html', 'index.html'] });
    const server = http.createServer((req, res) => {
        serve(req, res, finalhandler(req, res));
    });

    let browser;

    try {
        await new Promise(resolve => server.listen(PORT, resolve));
        console.log(`✅ 伺服器已在 http://127.0.0.1:${PORT} 上啟動`);

        // 2. 啟動 Playwright 瀏覽器
        browser = await chromium.launch();
        const page = await browser.newPage();

        // 3. 導航至目標頁面並進行驗證
        console.log(`🚀 正在導航至 ${TARGET_URL}...`);
        await page.goto(TARGET_URL, { timeout: 15000 });

        const actualTitle = await page.title();
        console.log(`📝 獲取到的頁面標題: "${actualTitle}"`);

        if (actualTitle !== EXPECTED_TITLE) {
            throw new Error(`標題驗證失敗！預期為 "${EXPECTED_TITLE}"，但實際為 "${actualTitle}"`);
        }

        console.log('🎉 輕量級快照腳本執行成功！頁面標題符合預期。');
        process.exitCode = 0; // 成功

    } catch (error) {
        console.error('❌ 快照腳本執行失敗:', error.message);
        process.exitCode = 1; // 失敗
    } finally {
        // 4. 確保瀏覽器和伺服器都被關閉
        if (browser) {
            await browser.close();
            console.log('🚪 瀏覽器已關閉');
        }
        await new Promise(resolve => server.close(resolve));
        console.log('🔌 伺服器已關閉');
    }
}

main();
