# 系統架構現況分析

## 系統架構圖 (v5 - 多工作者架構)

```mermaid
graph TD
    subgraph "使用者端 (Browser)"
        A[Vue.js 前端應用<br>(vue-app)]
    end

    subgraph "核心服務 (Core Services)"
        B[FastAPI 伺服器<br>(src/api/api_server.py)]
        D[資料庫管理器<br>(src/db/manager.py)]
        E[SQLite 資料庫<br>(database.db)]
    end

    subgraph "獨立工作者 (Standalone Workers)"
        W_YT[YouTube 工作者<br>run_youtube_worker.py]
        W_TS[轉錄工作者<br>run_transcription_worker.py]
        W_AI[AI 報告工作者<br>run_ai_report_worker.py]
    end

    subgraph "開發與測試 (Dev & Test)"
        F[Pytest/Playwright 測試套件<br>(e2e_tests)]
        G[開發啟動器<br>(runner/localrun_new.py)]
    end

    A -- "REST API / WebSocket" --> B
    B -- "任務排程/狀態查詢" --> D
    D -- "讀/寫" --> E

    %% Workers interact with the DB
    W_YT -- "讀/寫任務" --> D
    W_TS -- "讀/寫任務" --> D
    W_AI -- "讀/寫任務" --> D

    G -- "啟動/管理" --> B
    G -- "啟動/管理" --> D
    G -- "啟動/管理" --> W_YT
    G -- "啟動/管理" --> W_TS
    G -- "啟動/管理" --> W_AI
```

**文件更新日期：** 2025年8月19日
**作者:** Jules (AI Software Engineer)
**狀態:** 現行架構描述 (v5) - 更新為多工作者架構

---

## 1. 摘要 (Executive Summary)

本文件旨在描述「鳳凰音訊轉錄儀」專案當前的系統架構。在經歷了從靜態 HTML 到現代化 Web 應用的遷移後，系統已演進為一個職責清晰、前後端分離的架構。

目前的系統主要由三個核心部分組成：
1.  **Vue.js 前端**：一個位於 `vue-app/` 的現代化單頁應用程式 (SPA)，為使用者提供互動介面。
2.  **FastAPI 後端**：一個位於 `src/` 的 Python 後端，負責處理業務邏輯、任務管理以及與資料庫的通訊。
3.  **多工作者系統**：一系列位於根目錄的獨立 `run_*.py` 程序，負責執行如影片下載、音訊轉錄等耗時的背景任務。

本文件將詳細闡述這幾個部分的設計與互動方式。

---

## 2. 前端架構 (Frontend Architecture)

前端是一個基於 **Vue.js 3** 的單頁應用程式（SPA），原始碼存放於 `vue-app/` 目錄。

- **核心技術棧**:
    - **框架**: Vue.js 3 (Composition API)
    - **建置工具**: Vite
    - **套件管理**: Bun
    - **狀態管理**: Pinia
    - **HTTP 客戶端**: Axios

- **與後端通訊**:
    - **REST API**: 用於執行獲取任務列表、建立新任務等操作。
    - **WebSocket**: 用於接收任務狀態（如：進行中、已完成、失敗）的即時變更通知。

- **建置流程**:
    - 開發者需在 `vue-app/` 目錄下執行 `bun install` 和 `bun run build`。
    - 建置後的靜態檔案會被輸出到 `vue-app/dist/` 目錄，並由後端 FastAPI 伺服器直接提供服務。

---

## 3. 後端架構 (Backend Architecture)

後端由**核心服務**與**獨立工作者**兩部分組成，共同構成一個完整的系統。

- **核心服務**:
    - **服務入口 (`src/api/api_server.py`)**: 後端主應用，定義了所有 REST API 端點和 WebSocket 邏輯。在 `WORKER_MODE=new` 環境變數下，它負責將任務分派到佇列，而非親自執行。
    - **資料庫管理器 (`src/db/manager.py`)**: 一個獨立的伺服器行程，作為資料庫的唯一寫入點，避免了多程序寫入 SQLite 時的鎖定問題。

- **非同步任務 (獨立工作者)**:
    - 專案的背景任務處理已演進為**多工作者模式**。
    - 這些工作者是獨立的 Python 程序 (如 `run_youtube_worker.py`, `run_transcription_worker.py` 等)。
    - 它們會各自監聽資料庫中的任務佇列，領取特定類型的任務（如 `youtube_download`, `transcription`），執行後將結果寫回資料庫。
    - 這種架構提高了系統的模組化程度和可擴展性。
    - 舊的整合式 Worker (`src/tasks/worker.py`) 已被棄用，僅在部分舊的測試腳本中可能被呼叫。

---

## 4. 測試與開發環境

### 4.1. 測試架構 (Testing Architecture)

本專案的品質由位於 `e2e_tests/` 的端對端測試套件保證，其核心技術棧為 Pytest 與 Playwright。

- **伺服器生命週期管理 (`conftest.py`)**: 測試框架的核心，負責在執行測試時，自動啟動一個**簡化的**後端服務（通常只包含 API 伺服器和資料庫管理器），並在測試結束後自動關閉。
- **測試執行 (`runner/localtest.py`)**: 執行完整自動化測試套件的建議入口。

### 4.2. 開發環境啟動流程 (`runner/localrun_new.py`)

**本節由 AI (Jules) 於 2025年8月19日 補充**

主要的開發環境是透過 `runner/localrun_new.py` 腳本啟動的，它代表了應用程式最完整、最新的多工作者架構。

- **分段式啟動與網頁可用時機**:
    1.  **臨時狀態頁**：執行腳本後，會立即提供一個網址，但初期只會顯示一個「系統啟動中」的頁面。
    2.  **背景準備**：腳本會在背景執行安裝依賴、建置前端等耗時操作。
    3.  **服務啟動**：準備工作完成後，才會依序啟動資料庫、API 伺服器，以及所有的獨立工作者。
    4.  **健康檢查**：所有服務啟動後，啟動器會持續對 API 伺服器進行健康檢查。

- **結論**: **網頁達到「完整可用」狀態的準確時機是**：當執行 `localrun_new.py` 的終端機視窗中，顯示 `✅ 後端健康檢查成功。` 或 `✅✅✅ 伺服器已成功啟動！ ✅✅✅` 訊息時。在此之前，即使前端介面已顯示，後端功能也尚未就緒。

---

## 5. 主要依賴套件與資源分析

**本節由 AI (Jules) 於 2025年8月19日 新增**

專案的 `requirements-worker.txt` 中定義了幾個資源消耗較大的關鍵套件，主要由獨立工作者使用。

### 5.1. 重量級機器學習核心

-   **`torch` (PyTorch)**:
    -   **用途**: 深度學習框架，是 `faster-whisper` 的基礎。
    -   **大小**: 非常龐大，安裝檔大小約在 **500MB 至 2GB** 之間。
    -   **資源**: 執行時需要 **數 GB 的記憶體 (RAM)** 並會大量使用 **CPU 或 GPU**。

-   **`faster-whisper`**:
    -   **用途**: 高效能的語音轉文字模型。
    -   **大小**: 需要下載預訓練模型，大小可從數十 MB 至 **超過 1GB**。
    -   **資源**: 執行時需要約 **1GB 至 1.7GB 的記憶體**，並會顯著佔用 CPU 資源。

### 5.2. 通用工具與客戶端

-   **`yt-dlp`**:
    -   **用途**: 下載 YouTube 影片。
    -   **資源**: 主要消耗**網路頻寬**與**磁碟 I/O**。

-   **其他工具**: `pydub` (音訊處理), `google-generativeai` (API 客戶端), `opencc-python-reimplemented` (繁簡轉換), `WeasyPrint` (HTML 轉 PDF) 等，這些工具相對輕量，資源佔用較低。

**總結**: `run_transcription_worker.py` 和 `run_ai_report_worker.py` 是系統中資源需求最高的程序。
