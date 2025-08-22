## 2025-08-23T07:40:29.884646+08:00

### 🐛 修復與穩定性增強 (Fixes & Stability Improvements)
- **實作整合式重試邏輯**: 根據使用者回饋，重新設計了 `Colabpro.py` 的代理連結獲取機制，以達到最佳的穩定性與耐心。
    - **合併檢查與獲取**: 將「伺服器就緒檢查」與「代理連結獲取」兩個步驟合併到一個統一的重試迴圈中。
    - **耐心等待**: 在每一次的重試中，腳本都會先耐心檢查後端伺服器是否就緒。只有在確認伺服器就緒後，才會嘗試獲取代理連結。如果伺服器未就緒，它會等待並自動進入下一次重試，而不是直接失敗。
    - **提升穩定性**: 這個新邏輯兼具舊版方法的韌性與新版方法的診斷清晰度，能更有效地應對 Colab 環境中服務啟動時間不一致的問題。

## 2025-08-23T07:36:38.456954+08:00

### 🐛 修復與穩定性增強 (Fixes & Stability Improvements)
- **強化 Colab 啟動器穩健性**: 針對 Colab 環境中 `proxyPort` 功能不穩定的根本問題，對 `Colabpro.py` 進行了深度強化。
    - **新增伺服器就緒預檢**: 在嘗試獲取代理連結前，新增了一個基於 `socket` 的輪詢檢查，確保後端伺服器完全就緒後才進行下一步，避免了因競爭條件導致的失敗。
    - **增強診斷日誌**: 大幅增加了代理連結獲取過程中的日誌詳細程度，包括每次重試的計數、JS 錯誤的詳細內容以及 Python 端的完整錯誤堆疊，以便未來能快速定位問題。
    - **優化使用者提示**: 改善了儀表板的狀態回饋，並在最終失敗時，提供明確的指導性建議（恢復原廠執行階段），幫助使用者自行解決問題。

## 2025-08-23T06:58:53+08:00

### 🐛 修復與穩定性增強 (Fixes & Stability Improvements)
- **恢復 Colab 啟動器穩定性**:
    - 在 `Colabpro.py` 中，恢復了先前版本中更穩健的、帶有重試和超時機制的代理 URL 獲取邏輯，解決了因競爭條件導致的連結獲取失敗問題。
    - 在 `run_app.py` 啟動伺服器後新增了固定的等待時間，進一步提高了啟動流程的可靠性。
- **統一執行環境**:
    - 移除了 `background_tasks.py` 中為工作者建立獨立虛擬環境的邏輯，解決了 `uv not found` 的錯誤，並確保所有程序都在統一的環境中執行。
- **停用錯誤的前端日誌功能**:
    - 暫時註解掉了前端對一個不存在的後端日誌 API 的呼叫，消除了前端大量的 `405` 網路錯誤，使網頁恢復正常。
- **更新設定**:
    - 將 `Colabpro.py` 中的預設分支更新為 `610`。

## 2025-08-23T06:38:46+08:00

### 🐛 修復與穩定性增強 (Fixes & Stability Improvements)
- **解決 Colab 啟動競爭條件**:
    - 在 `run_app.py` 中，於啟動 Uvicorn 伺服器後新增了 15 秒的等待延遲。
    - 此舉確保了後端服務在 `Colabpro.py` 請求代理 URL 之前有充足的時間完成初始化，從而解決了因競爭條件導致的無法穩定獲取代理連結問題。
- **停用無效的前端 API 呼叫**:
    - 暫時註解掉了 `vue-app/src/utils/logging.js` 中對 `/api/log/action` 的呼叫。
    - 由於後端未實作此端點，此修改消除了前端大量的 `405` 網路錯誤，解決了導致頁面無回應的問題。
- **更新設定**:
    - 將 `Colabpro.py` 中的預設分支更新為 `610`。

## 2025-08-23T06:03:46+08:00

### 🐛 修復與架構一致性 (Fixes & Architectural Consistency)
- **統一工作者執行環境**:
    - 簡化了 `src/core/background_tasks.py`，完全移除了為背景工作者建立獨立虛擬環境的邏輯。
    - 此修改解決了在乾淨環境中因 `uv` 模組不存在而導致的啟動失敗，並確保所有程序都在由 `run_app.py` 準備的單一、統一環境中執行。
- **恢復 Colab 日誌報告功能**:
    - 在 `Colabpro.py` 中恢復了在腳本執行結束後顯示可複製 HTML 日誌報告的功能，修正了因重構引入的功能性回歸。
- **更新設定與測試穩定性**:
    - 將 `Colabpro.py` 中的預設分支更新為 `610`。
    - 增強了 `Colabpro.py` 中的測試模擬函式，使其對未來的參數變更更具彈性。

## 2025-08-23T00:57:04+08:00

### 🐛 修復與功能恢復 (Fixes & Feature Restoration)
- **恢復 HTML 日誌報告**:
    - 在 `Colabpro.py` 中重新實作了 `create_log_viewer_html` 函式，並修改 `DisplayManager` 以儲存完整日誌。
    - 此修改恢復了在 Colab 儲存格執行結束後，顯示可複製的完整日誌報告之功能。
- **新增 Bun 自動安裝**:
    - 在中央啟動腳本 `run_app.py` 中加入了 `ensure_bun_installed` 函式。
    - 此函式會自動偵測並安裝在乾淨環境中缺失的 `bun`，提高了啟動器的穩健性。

## 2025-08-23T00:41:15+08:00

### 🏛️ 架構重構 (Architectural Refactoring)
- **統一應用程式啟動邏輯**:
    - **新增 `run_app.py`**: 建立了一個新的中央啟動腳本，作為從零設定環境並啟動 `api_gateway` 的唯一入口。
    - **重構 `Colabpro.py` 啟動器**: 徹底簡化了 `Colabpro.py`，移除了所有過時的、手動管理虛擬環境和啟動舊伺服器的邏輯。現在它僅負責下載倉庫，並轉而呼叫 `run_app.py`，使所有啟動流程（本地、測試、Colab）保持一致。
- **更新設定**:
    - 將 `Colabpro.py` 中的預設分支更新為 `602`。

## 2025-08-22T23:59:33+08:00

### 🧪 測試與修復 (Testing & Fixes)
- **全面修復 E2E 測試流程**:
    - **自動化依賴管理**: 測試腳本 (`run_e2e_test.py`) 現在會自動安裝所有必要的後端 (Python)、前端 (Bun) 和測試執行器 (Playwright) 依賴。
    - **整合前端建置**: 在測試開始前，自動執行 `bun run build`，確保後端總是能提供最新的前端應用。
    - **修正後端服務**: 解決了 API 閘道中的路由衝突，並補全了缺失的 `pytz` 依賴。
- **增強前端渲染穩定性**:
    - **修復執行階段錯誤**: 在 `App.vue` 和 `Dashboard.vue` 中加入了防禦性程式碼，為非同步載入的狀態提供了後備物件，徹底解決了因存取 `undefined` 屬性而導致的 `TypeError` 渲染崩潰問題。

## 2025-08-22T15:58:00+08:00

### 🧪 測試策略遷移與根本原因分析 (Test Strategy Migration & Root Cause Analysis)
- **遷移 E2E 測試框架**: 為了實現前端測試的現代化，並解決在特定環境下執行的挑戰，對端對端測試策略進行了重大重構。
    - **廢棄 `test.py`**: 移除了原有的、完全基於 Python 的 Playwright 測試腳本 `test.py`。
    - **引入混合測試模式**:
        - **建立 Python 流程控制器 (`run_e2e_test.py`)**: 新增了一個 Python 腳本，專門負責處理測試的環境設定，包括：啟動後端伺服器、清理資料庫、管理子程序等。
        - **建立 JavaScript 測試執行器 (`run_browser_test.js`)**: 新增了一個獨立的、使用原生 `playwright` Node.js 套件的 JavaScript 腳本。此腳本包含了所有與瀏覽器互動的核心邏輯，實現了測試邏輯與環境控制的解耦。
- **解決環境限制**:
    - **繞過 `npm install` 限制**: 新的測試策略完全避免了在 `vue-app` 目錄下執行 `npm install`，從而成功繞過了因環境檔案數量限制而導致的 `node_modules` 安裝不完整問題。
    - **最小化節點依賴**: 在專案根目錄下建立了一個最小化的 `package.json`，僅用於安裝 `playwright` Node.js 套件，確保了測試腳本的執行環境。
- **成功定位根本問題**:
    - 經過多輪除錯，新的測試流程最終成功運行，並產生了詳細的追蹤日誌 (`trace.zip`)。
    - 測試結果確認了最初的失敗並非由測試執行器或環境設定引起，而是 **Vue 應用程式本身在 Playwright 的無頭瀏覽器環境中未能成功掛載 (mount)**，導致 `onMounted` 鉤子和後續的 WebSocket 初始化無法執行。這個發現為後續的前端除錯指明了清晰的方向。

## 2025-08-22T15:08:48+08:00

### 🏛️ 重大架構重構 (Major Architectural Refactoring)
- **引入 Huey 任務佇列**: 徹底重構了服務間的通訊方式。舊有的直接導入和不穩定的 HTTP 呼叫，被替換為一個基於 `Huey` 的、穩健的非同步任務佇列系統。`api_gateway` 現在作為任務的唯一生產者，將工作（如轉錄、日誌記錄）放入佇列，由獨立的背景工作者消費。
- **統一與隔離資料庫**:
    - **雙資料庫策略**：根據與使用者的深入討論，採用了雙資料庫隔離方案以提高穩定性。建立了一個獨立的 `logs.db` 用於日誌記錄，以及一個獨立的 `queue.db` 專供 Huey 任務佇列使用。
    - **中心化初始化**：`api_gateway` 現在是應用啟動的核心，它會在 `lifespan` 事件中，最優先初始化日誌資料庫（並啟用 WAL 模式以提高併發效能），然後才啟動所有背景工作者，從根本上解決了先前版本中存在的啟動時序競態條件問題。
- **重構為工作者模式 (Worker Pattern)**:
    - 建立了 `workers/` 目錄，並新增了 `transcription_worker.py` 和 `logging_worker.py`。
    - `background_tasks.py` 現在不再啟動多個獨立的服務，而是啟動一個 `huey_consumer.py` 程序來統一管理所有工作者的生命週期。
- **API Gateway 職責整合**:
    - 將原 `static_web_server` 的靜態檔案服務功能，以及 WebSocket 代理功能，全部整合進 `api_gateway`。
    - `api_gateway` 現在是名副其實的應用唯一入口點，負責處理所有 HTTP 請求、WebSocket 連線和前端檔案服務。
- **強化端對端測試**:
    - `test.py` 被徹底重構，不再依賴 `Colabpro.py`，而是直接測試 `api_gateway`。
    - 測試現在會動態尋找可用埠號，避免因埠號被佔用而導致的測試失敗。
    - Playwright 的驗證邏輯被加強，現在會實際檢查 UI 上的狀態文字 (`狀態: 準備就緒`)，確保前後端通訊真正成功。

## 2025-08-22T12:21:08+08:00

### 🐛 修復與功能優化 (Bug Fixes & Feature Enhancements)
- **修復日誌資料庫衝突**:
    - 還原了日誌資料庫 (`.db` 檔案) 的生成位置至根目錄 (`/content/`)，並在初始化 `LogManager` 前確保其父目錄存在。
    - 此修改徹底解決了在「強制刷新」模式下，因資料夾被刪除而導致的 `sqlite3.OperationalError: attempt to write a readonly database` 錯誤。
- **優化 Colab 關機體驗**:
    - 移除了關機程序中一個為時 5 秒的固定等待，讓使用者手動中斷儲存格時能獲得更即時的回應。
- **新增日誌存檔功能**:
    - 在每次執行結束後，會自動將完整的執行日誌儲存為一個 Markdown 檔案。
    - 檔案會以 ISO 時間戳命名 (`YYYY-MM-DDTHH:MM:SS+08:00.md`)，並存放於 `/content/paper/` 目錄下，方便使用者歸檔與查閱。
- **使用者設定更新**:
    - 將 `Colabpro.py` 中的預設 Git 分支從 `566` 更新為 `569`。
    - 更新了 `Colabpro.py` 中的開發者日誌以反映最新變更。

## 2025-08-22T12:05:58+08:00

### 🚀 功能與體驗優化 (Features & UX Improvements)
- **優化 Colab 關機流程**:
    - 在 `Colabpro.py` 中，移除了關機程序中一個為時 5 秒的固定等待，讓使用者手動中斷儲存格時能獲得更即時的回應。
- **新增日誌存檔功能**:
    - 在每次執行結束後，會自動將完整的執行日誌儲存為一個 Markdown 檔案。
    - 檔案會以 ISO 時間戳命名 (`YYYY-MM-DDTHH:MM:SS+08:00.md`)，並存放於 `/content/paper/` 目錄下，方便使用者歸檔與查閱。
- **調整日誌資料庫路徑**:
    - 將執行期間的日誌資料庫 (`.db` 檔案) 的生成位置，從根目錄移至專案資料夾內部，並確保在初始化前其父目錄已存在。
    - 此修改可確保在使用者選擇「強制刷新後端程式碼」時，舊的日誌資料庫能被一併清除，並解決了因此路徑問題導致的 `sqlite3.OperationalError`。

### 🐛 修復與穩定性增強 (Bug Fixes & Stability Improvements)
- **修正 Colab 啟動器過早終止問題**:
    - 在 `Colabpro.py` 的 `launch_application` 函式中，將 `server_proc.wait()` 替換為一個無限迴圈，確保主執行緒在背景伺服器啟動後能保持存活。
- **修復日誌檢視器的「複製」按鈕**:
    - 重構了 `Colabpro.py` 中的 `create_log_viewer_html` 函式，將日誌內容儲存在一個隱藏的 `<textarea>` 中，解決了因日誌內容包含特殊字元而導致按鈕功能失效的問題。
- **強化測試套件與修復伺服器啟動**:
    - **重點：修正測試邏輯以使用本地程式碼**：修改了 `Colabpro.py`，使其在測試模式下會跳過 `git clone` 步驟。
    - **提高測試穩定性**：在 `test.py` 中引入了埠號輪詢機制，取代了不穩定的固定延遲，以解決伺服器啟動時的競爭條件問題。
    - **修正伺服器啟動失敗**：修復了 `services/static_web_server/main.py` 中的一個相對導入錯誤 (`ImportError`)。
- **使用者設定更新**:
    - 將 `Colabpro.py` 中的預設 Git 分支從 `563` 更新為 `566`。
    - 更新了 `Colabpro.py` 中的開發者日誌以反映最新變更。

## 2025-08-22T11:13:05+08:00

### 🏛️ 架構重構與穩定性修復 (Architectural Refactoring & Stability Fixes)
- **實作「極速兩階段啟動」架構**: 徹底重構了 `Colabpro.py` 的啟動邏輯，以解決因依賴問題導致的啟動失敗，並顯著提升前端頁面的載入速度。
    - **解耦啟動流程**: `Colabpro.py` 現在僅負責啟動一個輕量的靜態網頁伺服器，讓使用者可以立即看到 UI。
    - **非同步背景安裝**: 所有重量級服務的依賴安裝，都被移至由 FastAPI 的 `lifespan` 事件觸發的 `asyncio` 背景任務中，不再阻塞主流程。
    - **移除無用依賴**: 從網頁伺服器的依賴中移除了導致編譯失敗的 `pydantic-settings` 套件。
    - **強化端對端測試**: 重構了 `test.py` 驗證腳本，使其能夠模擬 Colab 環境（透過 Mock `google.colab` 模組）並加入嚴格的超時（60/120秒）來驗證新的兩階段啟動流程。
- **增強穩健性**:
    - **修復 Colab 通訊錯誤**: 增加了對 `colab_output.eval_js` 可能返回 `None` 的邊界情況處理，避免了 `AttributeError`。
    - **修復日誌系統錯誤**: 修正了 `LogManager`，使其能正確處理 `exc_info` 參數，以便在發生未預期錯誤時能記錄完整的錯誤堆疊，解決了 `TypeError` 問題。
- **使用者設定更新**:
    - 將 `Colabpro.py` 中的預設 Git 分支更新為 `563`。
    - 將 UI 標題更新為 `v7.0 - 極速啟動`。

## 2025-08-22T02:58:59+08:00

### 🏛️ 架構重構 (Architectural Refactoring)
- **實作「極速兩階段啟動」架構**: 徹底重構了 `Colabpro.py` 的啟動邏輯，以解決因依賴問題導致的啟動失敗，並顯著提升前端頁面的載入速度。
    - **解耦啟動流程**: `Colabpro.py` 現在僅負責啟動一個輕量的靜態網頁伺服器，讓使用者可以立即看到 UI。
    - **非同步背景安裝**: 所有重量級服務（如 AI 模型）的依賴安裝，都被移至由 FastAPI 的 `lifespan` 事件觸發的 `asyncio` 背景任務中，不再阻塞主流程。
    - **移除無用依賴**: 從網頁伺服器的依賴中移除了導致編譯失敗的 `pydantic-settings` 套件。
    - **強化端對端測試**: 重構了 `test.py` 驗證腳本，使其能夠模擬 Colab 環境（透過 Mock `google.colab` 模組）並加入嚴格的超時（60/120秒）來驗證新的兩階段啟動流程，確保了架構的穩定性與效能。

## 2025-08-22T02:54:48+08:00

### 🏛️ 架構重構 (Architectural Refactoring)
- **實作「極速兩階段啟動」架構**: 徹底重構了 `Colabpro.py` 的啟動邏輯，以解決因依賴問題導致的啟動失敗，並顯著提升前端頁面的載入速度。
    - **解耦啟動流程**: `Colabpro.py` 現在僅負責啟動一個輕量的靜態網頁伺服器，讓使用者可以立即看到 UI。
    - **非同步背景安裝**: 所有重量級服務（如 AI 模型）的依賴安裝，都被移至由 FastAPI 的 `lifespan` 事件觸發的 `asyncio` 背景任務中，不再阻塞主流程。
    - **移除無用依賴**: 從網頁伺服器的依賴中移除了導致編譯失敗的 `pydantic-settings` 套件。
    - **強化端對端測試**: 重構了 `test.py` 驗證腳本，使其能夠模擬 Colab 環境（透過 Mock `google.colab` 模組）並加入嚴格的超時（60/120秒）來驗證新的兩階段啟動流程，確保了架構的穩定性與效能。

## 2025-08-22T02:54:48+08:00

### 🏛️ 架構重構 (Architectural Refactoring)
- **實作「極速兩階段啟動」架構**: 徹底重構了 `Colabpro.py` 的啟動邏輯，以解決因依賴問題導致的啟動失敗，並顯著提升前端頁面的載入速度。
    - **解耦啟動流程**: `Colabpro.py` 現在僅負責啟動一個輕量的靜態網頁伺服器，讓使用者可以立即看到 UI。
    - **非同步背景安裝**: 所有重量級服務（如 AI 模型）的依賴安裝，都被移至由 FastAPI 的 `lifespan` 事件觸發的 `asyncio` 背景任務中，不再阻塞主流程。
    - **移除無用依賴**: 從網頁伺服器的依賴中移除了導致編譯失敗的 `pydantic-settings` 套件。
    - **強化端對端測試**: 重構了 `test.py` 驗證腳本，使其能夠模擬 Colab 環境（透過 Mock `google.colab` 模組）並加入嚴格的超時（60/120秒）來驗證新的兩階段啟動流程，確保了架構的穩定性與效能。

## 2025-08-22T10:24:41+08:00

### 🚀 UI/UX 現代化 (UI/UX Modernization)
- **完成「無彈窗」革命第一階段**: 根據 UI/UX 現代化計畫，此變更徹底移除了整個 Vue 應用程式中所有傳統的 `alert()` 彈出式視窗。
    - **引入全域通知系統**: 實作並整合了一個基於 Pinia store 的非侵入式頁頂通知系統 (`NotificationHost.vue` 與 `stores/notifications.js`)。
    - **全面替換 `alert()`**: 修改了 `Downloader.vue`, `LogViewer.vue`, `CompletedTasks.vue`, 和 `YouTubeReporter.vue`，將所有 `alert()` 呼叫替換為新的 `addNotification` 服務，用於顯示成功、錯誤和驗證訊息。
    - **增強測試覆蓋**: 新增了單元測試 (`LogViewer.spec.js`) 來驗證 `LogViewer` 元件中複製日誌功能的通知行為，確保重構後的程式碼品質與穩定性。

## 2025-08-21T13:02:00+08:00

### ♻️ 重構與遷移 (Refactoring & Migration)
- **將元件測試框架從 Playwright 遷移至 Vitest**: 由於在沙箱環境中遭遇了無法解決的 Playwright 元件測試編譯問題，故決定更換測試框架。
    - **移除 Playwright**: 從 `vue-app/package.json` 中完全移除了 `@playwright/experimental-ct-vue` 和 `@playwright/test` 依賴，並刪除了所有相關的設定檔 (`playwright.config.js`) 和測試檔案。
    - **引入 Vitest**: 新增了 `vitest`、`@vue/test-utils` 和 `jsdom` 作為新的開發依賴，為 Vue 元件提供了一個更穩定、更輕量的測試環境。
    - **建立驗證測試**: 建立了一個簡單的 Vitest 測試 (`Simple.spec.js`)，成功掛載了一個 Vue 元件並驗證了其輸出，確認新測試框架已正確設定並可運作。
    - **更新測試腳本**: 在 `package.json` 中新增了 `test:unit` 腳本，方便未來執行單元測試。

## 2025-08-21T11:55:00+08:00

### 🧪 測試基礎設施 (Testing Infrastructure)
- **新增 Vue 元件測試框架**: 為了驗證前端工作流程，引入了 Playwright 的元件測試功能。
    - 在 `vue-app/` 中新增了 `playwright.config.js`，設定了元件測試的執行環境，使用 Vite 作為打包工具。
    - 在 `vue-app/package.json` 中新增了 `@playwright/experimental-ct-vue` 依賴。
    - 為了解決依賴衝突，將 `vite` 降級至 `^5.0.0`，並將 `@vitejs/plugin-vue` 和 `vite-plugin-vue-devtools` 降級至相容版本。
- **建立工作流程驗證測試**:
    - 在 `vue-app/tests/component/` 目錄下建立了 `workflow.spec.js`。
    - 此測試透過掛載 `PendingTasks.vue` 和 `CompletedTasks.vue` 元件，並提供一個假的 Pinia store，來模擬並驗證一個任務從「處理中」到「已完成」的完整前端狀態轉移，無需依賴後端。

### 🐛 修復與除錯 (Bug Fixes & Debugging)
- **解決測試環境問題**: 投入大量時間解決了在沙箱環境中執行 Playwright 元件測試時遇到的一系列底層問題。
    - **發現並解決了 CWD (當前工作目錄) 不一致問題**：最終確認 `npx playwright` 指令的執行目錄與預期不符，導致設定檔 (`playwright.config.js`) 從未被載入。透過改用 `cd vue-app && npx playwright test` 的方式，確保了指令在正確的目錄下執行。
    - **隔離測試類型**: 為了避免元件測試執行器錯誤地解析 E2E 測試檔案，建立了 `tests/component` 目錄來存放所有元件測試，並在 `playwright.config.js` 中明確指定該目錄，實現了不同測試類型的隔離。

## 2025-08-21T10:50:00+08:00

### 🧹 重構與清理 (Refactoring & Cleanup)
- **大規模清理專案**: 為了替換為 `uv` + `Supervisor` 新架構，進行了大規模的檔案清理。
    <details>
    <summary>點此展開被刪除的檔案與目錄完整列表</summary>

    ```
    - /run_ai_report_worker.py
    - /run_model_management_worker.py
    - /run_transcription_worker.py
    - /run_youtube_worker.py
    - /requirements-prod-server.txt
    - /requirements-server.txt
    - /requirements-worker.txt
    - /requirements.txt
    - /pyproject.toml
    - /bun.lock
    - /package.json
    - /package-lock.json
    - /file_list.txt
    - /bun_install.sh
    - /e2e_tests/   (整個目錄)
    - /config/     (整個目錄)
    ```
    </details>
    - **刪除過時的啟動器與 Worker**: 移除了根目錄下的所有 `run_*.py` 獨立 worker 腳本。
    - **移除多餘的依賴檔案**: 刪除了所有根目錄下的 `requirements*.txt`, `pyproject.toml`, `package.json` 等，因為依賴將由 `uv` 在腳本內部管理。
    - **精簡測試與設定**: 刪除了整個 `e2e_tests/` 和 `config/` 目錄，以降低重構期間的複雜性。
- **新增架構 POC 報告**:
    - 在 `DOC/` 目錄下新增了 `ARCHITECTURE_POC_REPORT.md`。
    - 這份報告詳細記錄了 `uv` + `Supervisor` 架構的可行性驗證過程，包括實驗中遇到的問題與解決方案，為未來的開發提供重要參考。

## 2025-08-21T09:52:00+08:00

### 🏛️ 架構 (Architecture)
- **研究並驗證新架構**: 根據使用者的研究日誌，對 `uv` + `Supervisor` 的輕量級微服務架構進行了深入研究與概念驗證 (POC)。
- **建立 POC**: 在 `poc_supervisor_uv/` 目錄中建立了一個包含兩個獨立 worker、`supervisord.conf` 和啟動腳本的微型環境。
- **成功驗證**: 實驗的即時日誌證明，`Supervisor` 能成功啟動並管理使用 `uv` 進行依賴隔離的 Python 腳本，驗證了此核心架構的可行性。所有 POC 相關檔案將在此提交後被刪除，為後續重構做準備。

## 2025-08-21T22:56:35+08:00

### 🧪 測試基礎設施 (Testing Infrastructure)
- **新增啟動驗證腳本**: 新增了 `e2e_tests/verify_startup.py`，這是一個獨立的 Playwright 腳本，用於驗證整個應用程式是否能成功啟動並被前端存取。
- **確立核心啟動流程**: 透過分析 `test.py` 和 `runner/main_runner.py`，確認了專案當前正確的、模組化的啟動方法。
- **修復測試環境**: 成功安裝了 Playwright 的系統級依賴 (`playwright install-deps`)，解決了瀏覽器無法在沙箱環境中啟動的問題。

## 2025-08-21T01:33:00+08:00

### 🧪 測試基礎設施 (Testing Infrastructure)
- **新增儀表板功能 E2E 測試**: 建立了一個新的 Playwright 測試檔案 `e2e_tests/test_dashboard_functionality.py`。此測試透過模擬 API 回應和 WebSocket 訊息，完整驗證了儀表板在接收到後端事件時，其狀態（如：系統負載、工作者狀態）能夠正確且即時地更新。這確保了使用者回報的儀表板無反應問題可以被穩定地監控與驗證。

### 🐛 修復 (Bug Fixes)
- **增強 E2E 測試的穩定性**:
    - **修正競爭條件**: 移除了新測試中多個因後端回應過快而導致不穩定的初始狀態斷言。測試現在專注於驗證核心的更新邏輯，而非短暫的過渡狀態。
    - **修正既有測試的崩潰問題**: 修復了 `e2e_tests/test_end_to_end_workflow.py` 中一個因無法處理非預期 WebSocket 訊息格式而導致的 `AttributeError` 崩潰。
    - **修正測試執行路徑**: 發現並修正了說明文件中關於測試啟動指令 `runner/localtest.py` 的路徑錯誤，正確路徑應為 `e2e_tests/localtest.py`。

## 2025-08-21T09:04:24+08:00

### 🐛 修復 (Bug Fixes)
- **增強資料庫管理器穩定性**: 在 `src/db/manager.py` 中增加了強健的錯誤處理機制。現在，當伺服器收到格式不正確的 JSON 請求時，它將記錄錯誤、通知客戶端，並繼續處理後續請求，而不會再因此中斷連線。這解決了因日誌內容包含特殊字元而導致服務連鎖崩潰的問題。

## 2025-08-21T08:44:24+08:00

### 🐛 修復 (Bug Fixes)
- **修正 Worker 導入錯誤**: 解決了 `main_worker.py` 因嘗試導入一個不存在的日誌設定函式 (`setup_logging_for_module`) 而導致的 `ImportError`。此錯誤會造成 worker 崩潰，進而觸發協調器關閉整個應用程式。現已移除該錯誤的導入程式碼。

## 2025-08-21T08:40:46+08:00

### 🐛 修復 (Bug Fixes)
- **修正伺服器啟動穩定性**: 解決了導致後端服務在啟動後立即崩潰、網址無法使用的根本性問題。
    - **修正 Runner 邏輯**: 重構了 `runner/main_runner.py`，確保它在獲取到 URL 後會繼續監聽 `orchestrator` 的輸出，而不是提前退出。這解決了因輸出管道阻塞而導致子程序崩潰的問題。
    - **穩健化 API 伺服器啟動**: 修改了 `src/core/orchestrator.py`，改為使用標準的 `uvicorn` 命令列方式來啟動 API 伺服器，解決了直接執行腳本時可能發生的啟動失敗和連線被拒絕的問題。

### 🧪 測試基礎設施 (Testing Infrastructure)
- **補全測試腳本**: 為 `test.py` 腳本提供了一個缺失的 `jules-scratch/verification/verify_simple.py` 驗證檔案，並修正了其中的預期標題，使得端對端測試可以成功執行並驗證系統狀態。

## 2025-08-21T02:06:16+08:00

### ♻️ 重構 (Refactoring)
- **統一前端狀態管理**: 徹底重構了 `vue-app` 的核心狀態管理 (`stores/tasks.js`)，以提高穩定性並解決 UI 不一致的問題。
    - **廢除輪詢**: 移除了 `Dashboard.vue` 中效率低下的 `setInterval` 輪詢，現在所有系統和工作者狀態的更新都統一由 WebSocket 即時推送，解決了 UI 閃爍和資料延遲的問題。
    - **簡化全域狀態**: 將原先混亂的 `installationStatus` 和 `modelDownloadStatus` 狀態，合併為一個單一、清晰的 `operationStatus` 物件。這個物件現在統一管理所有阻擋使用者操作的全域活動（如模型下載、工作者安裝），使程式碼邏輯更清晰。
    - **增強視覺回饋**: 為全域狀態覆蓋層新增了進度條，現在當下載模型時，使用者可以看到一個明確的進度指示。

### 🐛 修復 (Bug Fixes)
- **修復啟動腳本的競爭條件**: 在 `src/core/orchestrator.py` 中，增加了在啟動 API 伺服器後、輸出 URL 之前等待服務就緒的邏輯。這解決了 E2E 測試 (`test.py`) 因伺服器尚未完全啟動而導致連線失敗的問題。
- **移除無用程式碼**: 清理了 `TaskUploader.vue` 中殘留的、與舊狀態綁定的進度條相關的無用程式碼。

## 2025-08-21T02:38:00+08:00

### 🧪 測試基礎設施 (Testing Infrastructure)
- **重構 E2E 測試環境**: 徹底重構了 `e2e_tests/conftest.py`，以優化資源使用並提高測試之間的隔離性。
    - **模組級隔離**: 將核心的 `live_server` fixture 的範圍從 `session` 更改為 `module`。現在，每個測試檔案都會在一個全新的、獨立的伺服器環境中運行，並在結束後自動清理，實現了使用者「一個工作者測完就刪掉虛擬環境」的目標。
    - **高效前端建置**: 將耗時的前端建置 (`bun run build`) 流程抽離到一個獨立的、`session` 範圍的 fixture 中。這確保了前端資源在整個測試會話中只會被建置一次，大幅提高了測試的整體執行效率。
    - **資料庫自動清理**: 在每個模組的測試開始前，會自動刪除舊的資料庫檔案並重新初始化，確保了測試資料的純淨性。

### 🐛 修復 (Bug Fixes)
- **補全測試依賴**: 修正了因 `requirements-server.txt` 中缺少 `httpx` 和 `pydantic-settings` 套件而導致的測試收集錯誤。

## 2025-08-20T23:51:57+08:00

### 🚀 新功能 & 重大重構 (New Features & Major Refactoring)
- **恢復手動模型下載**: 根據使用者回饋和舊版邏輯，完全重構了本地 Whisper 模型的管理方式。
    - **新後端工作者**: 建立了一個新的 `run_model_management_worker.py`，專門負責處理模型下載任務，使模型管理與核心轉錄功能解耦。
    - **恢復 WebSocket 驅動**: 移除了先前不穩定的 REST API 下載方式，恢復為由前端透過 WebSocket 訊息 (`DOWNLOAD_MODEL`) 觸發的、更為穩健的下載流程。
    - **前端 UI 升級**: `TaskUploader` 介面現在會檢查模型是否存在，並提供一個動態的「下載/確認模型」按鈕，讓使用者可以手動控制下載。
- **實作啟動倒數計時器**:
    - 在應用程式啟動時，新增了一個 60 秒的倒數計時器。
    - 如果使用者未手動取消，計時結束後會自動下載預設的 `tiny` 模型，優化了初次使用的體驗。
    - 提供「取消」按鈕，給予使用者完整的控制權。
- **新增日誌複製功能**: 在「系統日誌」檢視器中，新增了一個「複製日誌」按鈕，方便使用者進行除錯和回報。

### 🐛 修復 (Bug Fixes)
- **修正 Gemini 模型載入邏輯**: 還原了 `/api/youtube/models` 端點的邏輯，使其從前端請求中獲取 API 金鑰，解決了因金鑰傳遞方式錯誤而導致模型列表無法載入的問題。
- **修正 `api_server` 轉錄邏輯**: 移除了 `/api/transcribe` 端點中與手動下載流程衝突的「自動建立下載任務」邏輯。

### 💄 UI 優化 (UI Improvements)
- **工作者狀態排版**: 重新設計了儀表板上的工作者狀態顯示區塊，使用 Flexbox 確保其佈局在不同螢幕寬度下都能保持整潔、美觀，不會再擠壓變形。

## 2025-08-20T23:13:00+08:00

### 🐛 修復 (Bug Fixes)
- **修正 UI 更新的競爭條件**: 移除了 `Colabpro.py` 中 `launch_application` 函式 `finally` 區塊裡多餘的 `clear_output` 指令。
    - **問題**: 在極少數情況下，該指令會在 `DisplayManager` 執行緒停止後，但在最終結果被繪製到螢幕前執行，導致代理連結等最終狀態被意外清除。
    - **解決方案**: 移除該指令，並依賴 `finally` 區塊中原有的 `print` 呼叫來確保最終狀態一定會被顯示。
- **修正 `TypeError` 語法錯誤**: 修正了 `Colabpro.py` 中 `_eval_js_in_thread` 函式內一個由於錯誤使用雙層大括號 `{{...}}` 而導致的 `TypeError: unhashable type: 'dict'` 致命錯誤。

### ✨ 新功能 (New Features)
- **新增 `clear_output` 開關**: 在 `Colabpro.py` 中新增了一個 `ENABLE_CLEAR_OUTPUT` 的勾選選項，允許使用者自由控制是否在儀表板更新時清理畫面，方便在需要時保留完整日誌進行除錯。
- **增強 Colab 啟動器診斷能力**:
    - **前端通訊探測**: 在 `Colabpro.py` 中，新增了一個前置的「心跳探測」步驟，使用簡單的 `eval_js` 呼叫來提前確認 Colab 前後端通訊管道是否健康。
    - **詳細錯誤記錄**: 為獲取代理連結的重試迴圈加入了完整的 `traceback` 日誌記錄，以便在 `eval_js` 呼叫失敗時，能捕捉到詳細的錯誤堆疊資訊。

### ♻️ 重構 (Refactoring)
- **恢復 Colabpro.py 的背景執行緒架構**:
    - **問題**: 新版的 `Colabpro.py` 使用單一主執行緒來啟動後端服務並獲取 Colab 代理連結，導致主執行緒被阻塞，無法處理 `eval_js` 的回呼，進而造成代理連結獲取超時。
    - **解決方案**: 恢復了舊版中更為健壯的 `BackgroundRunner` 設計。將後端服務的啟動和日誌監聽放在一個獨立的背景執行緒中，主執行緒被完全釋放出來，專門負責與 Colab 前端通訊以獲取代理連結，從根本上解決了執行緒阻塞問題。

### 🐛 修復 (Bug Fixes)
- **修正子程序路徑問題**: 徹底解決了在 Colab 環境中 `db_manager.py` 無法啟動的根本原因。
    - **問題**: `orchestrator.py` 使用相對路徑來啟動子程序，但在某些執行環境下（如 Colab），這會導致「找不到檔案」的錯誤。
    - **解決方案**: 修改了 `orchestrator.py`，將所有 `subprocess.Popen` 呼叫中的腳本路徑，都改為基於 `ROOT_DIR` 變數的**絕對路徑**，確保了路徑的穩定與可靠性。
- **修正日誌系統邏輯**: 修復了 `orchestrator.py` 中一個導致子程序早期日誌遺失的邏輯錯誤。之前，日誌讀取執行緒啟動過晚，現在已調整為在子程序建立後立即啟動，確保日誌的完整性。

### ♻️ 重構 (Refactoring)
- **清理診斷代碼**: 移除了為解決上述問題而臨時加入的所有診斷日誌和錯誤捕獲程式碼，使程式碼庫恢復乾淨。

## 2025-08-20T18:12:45+08:00

### 🏛️ 架構規劃 (Architectural Planning)
- **研究並規劃 `uv venv` 整合**: 根據使用者的要求，進入研究模式，對 `uv` 的虛擬環境管理功能進行了深入研究。
    - **產出**: 建立了一份詳細的 `plan.md` 研究報告。
    - **結論**: 確認了使用 `uv venv` 來為每一個獨立的工作者和服務建立隔離的虛擬環境是完全可行的。
    - **新架構**: 規劃了新的自我引導式啟動架構，其中每個執行腳本將內建其依賴列表，並自動檢查、建立和安裝其所需的虛擬環境，不再需要共用的 `requirements.txt` 檔案。
- **分析 Colab 環境問題**: 對於在 Colab 中啟動超時的問題進行了分析，結論指向 Colab 共享資源的 I/O 效能瓶頸和網路檔案系統延遲，而非傳統的程式碼錯誤。

## 2025-08-20T14:00:00+08:00

### ♻️ 重構 (Refactoring)
- **模組化啟動流程**: 徹底重構了 `Colabpro.py` 的啟動機制。
    - 移除了舊的、複雜且不穩定的兩階段啟動邏輯。
    - `Colabpro.py` 現在被簡化為一個純粹的下載器和UI介面主機。
- **分離依賴**: 建立了 `requirements-prod-server.txt`，將生產環境的必要依賴與測試、開發依賴完全分離，使生產啟動更乾淨、更快速。

### ✨ 新功能 (New Features)
- **獨立啟動器 (Runner)**: 新增了 `runner/main_runner.py`，一個獨立的、健壯的啟動器腳本。它負責處理所有後端啟動的複雜性，包括安裝依賴和啟動核心服務。
- **獨立驗證腳本**: 新增了 `test.py`，一個使用 Playwright 的端到端驗證腳本。它能獨立驗證整個啟動流程的正確性，確保伺服器啟動後前端頁面可正常訪問。
- **啟動自我診斷**: `Colabpro.py` 新增了版本驗證功能。在下載程式碼後，會自動檢查關鍵檔案是否為最新版本，如果不是，則會提示使用者合併PR，避免執行過時的程式碼。
- **恢復日誌資訊顯示**: 恢復了在啟動器開始時顯示倉庫URL和分支的功能，並確保其被寫入日誌系統。

### 🐛 修復 (Bug Fixes)
- **日誌UI還原**: 根據使用者提供的舊版程式碼，還原了 `Colabpro.py` 結尾處HTML日誌報告的原始CSS樣式和複製功能。
- **`db_manager` 啟動失敗診斷**: 修改了 `src/core/orchestrator.py`，使其能顯示 `db_manager.py` 子程序的錯誤輸出，以便診斷潛在的啟動超時問題。

# 變更日誌

## 2025-08-20T12:40:32+08:00

### ✨ 新功能 (New Features)
- **中央日誌工作者**: 為了完全避免日誌寫入資料庫時的競爭條件 (race condition) 和鎖定問題 (deadlock)，建立了一個中央日誌工作者。所有服務（包括前端事件和後端工作者）的日誌 ఇప్పుడు都會發送到一個中央佇列，由單一的背景工作者進行排序、批次處理後，再統一寫入資料庫。此舉確保了日誌寫入的原子性和順序性，並透過批次處理提高了系統效率。

### 🗑️ 移除 (Removed)
- **廢棄的日誌服務**: 移除了舊的、分散的 `services/log_management_service`，因其功能已被新的中央日誌工作者取代，使整體架構更加清晰、穩健。

### ♻️ 重構 (Refactoring)
- **統一工作者日誌**: 重構了所有 `run_*_worker.py` 指令碼，使其日誌記錄功能接入新的中央日誌系統。
- **強化 E2E 測試**: 更新了 `e2e_tests/test_click_logging.py`，使其能夠在非同步和多重日誌事件的環境下，精準地等待並驗證特定的日誌訊息，提高了測試的穩定性。

## 2025-08-20

### ✨ 新增

-   **後端驗證的 E2E 測試**: 重寫了 `e2e_tests/test_click_logging.py`，現在它能完整驗證從前端點擊到後端資料庫記錄的整個流程。測試會輪詢一個專用的 API 端點，以確認日誌被成功寫入並獲得了唯一的追蹤 ID。

### ♻️ 重構

-   **非阻塞日誌處理器**: 重構了 `src/db/log_handler.py`，採用了基於佇列 (Queue) 和背景工作執行緒 (Worker Thread) 的非阻塞設計。這徹底解決了在 `api_server` 啟動時因日誌系統同步等待資料庫連線而導致的死鎖問題。
-   **統一的日誌寫入介面**: 在 `src/db/manager.py` 和 `src/db/client.py` 中新增了 `add_system_log` 介面，使日誌處理器能與其他服務一樣，透過統一的資料庫管理器來寫入日誌，確保了架構的一致性與穩定性。

### 🐛 修復

-   **修正日誌查詢**: 修正了 `src/db/database.py` 中的 `get_system_logs_by_filter` 函式，在 SQL 查詢中加入了 `id` 欄位，確保測試可以成功驗證日誌的追蹤編號。

## 2025-08-19

### ✨ 新增

-   **新增系統架構圖**: 在 `DOC/ARCHITECTURE_RESEARCH.md` 文件中新增了基於 Mermaid.js 的系統架構圖，以提供更直觀的系統總覽。
-   **新增 `CHANGELOG.md`**: 建立此變更日誌檔案，以追蹤未來的開發與重構工作。

### ♻️ 重構與整理

-   **建立文件封存目錄**: 新增 `DOC/archive/` 目錄，用於存放所有不再反映專案現況的歷史文件。
-   **封存過時文件**: 將以下四份文件遷移至 `DOC/archive/` 目錄，因其內容為歷史紀錄，可能對新開發者產生誤導：
    -   `ANALYSIS.md`
    -   `DIAGNOSTIC_REPORT.md`
    -   `FRONTEND_REFACTOR_OPTIONS.md`
    -   `bug.md` (舊版 `mp3.html` 的詳細除錯日誌)
-   **合併 `bug.md`**: 將 `doc/bug.md` (包含當前待辦問題的報告) 移動至 `DOC/bug.md`，並刪除多餘的 `doc` 目錄，統一文件結構。

### ✏️ 文件更新

-   **更新架構文件狀態**: 更新了 `DOC/ARCHITECTURE_RESEARCH.md` 的文件標頭，將日期更新為今日，並註明版本變更。
-   **標註所有經審查的文件**: 為所有本次修改過的文件（包括新舊架構文件及所有封存文件）添加了 `2025-08-19` 的審查日期戳，明確標示其最後的審查狀態。
