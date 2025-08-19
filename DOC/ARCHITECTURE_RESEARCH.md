# 系統架構現況分析

## 系統架構圖

```mermaid
graph TD
    subgraph "使用者端 (Browser)"
        A[Vue.js 前端應用<br>(vue-app)]
    end

    subgraph "後端服務 (Backend Services)"
        B[FastAPI 伺服器<br>(src/api/api_server.py)]
        C[非同步任務工作器<br>(src/tasks/worker.py)]
        D[資料庫管理器<br>(src/db/manager.py)]
        E[SQLite 資料庫<br>(database.db)]
    end

    subgraph "開發與測試 (Dev & Test)"
        F[Pytest/Playwright 測試套件<br>(e2e_tests)]
        G[測試啟動器<br>(runner/localtest.py)]
    end

    A -- "REST API (HTTP)<br>WebSocket (WSS)" --> B
    B -- "任務排程/狀態查詢" --> D
    C -- "讀取待辦任務/寫入結果" --> D
    D -- "讀/寫" --> E
    B -- "提供靜態檔案" --> A

    G -- "執行" --> F
    F -- "啟動/管理" --> B
    F -- "啟動/管理" --> D
    F -- "與前端互動" --> A
```

**文件更新日期：** 2025年8月19日
**作者:** Jules (AI Software Engineer)
**狀態:** 現行架構描述 (v4) - 已新增系統架構圖

---

## 1. 摘要 (Executive Summary)

本文件旨在描述「鳳凰音訊轉錄儀」專案當前的系統架構。在經歷了從靜態 HTML 到現代化 Web 應用的遷移後，系統已演進為一個職責清晰、前後端分離的架構。

目前的系統主要由三個核心部分組成：
1.  **Vue.js 前端**：一個位於 `vue-app/` 的現代化單頁應用程式 (SPA)，為使用者提供互動介面。
2.  **FastAPI 後端**：一個位於 `src/` 的 Python 後端，負責處理業務邏輯、任務管理以及與資料庫的通訊。
3.  **Pytest/Playwright 測試套件**：一個位於 `e2e_tests/` 的端對端測試框架，透過自動化的伺服器生命週期管理，確保了程式碼的品質與穩定性。

本文件將詳細闡述這三個部分的設計與互動方式。

---

## 2. 前端架構 (Frontend Architecture)

前端是一個基於 **Vue.js 3** 的單頁應用程式（SPA），原始碼存放於 `vue-app/` 目錄。

- **核心技術棧**:
    - **框架**: Vue.js 3 (Composition API)
    - **建置工具**: Vite
    - **套件管理**: Bun
    - **狀態管理**: Pinia
    - **HTTP 客戶端**: Axios

- **狀態管理 (`stores/tasks.js`)**:
    - 所有與任務相關的客戶端狀態都由 Pinia 統一管理。
    - 它負責從後端獲取任務列表、透過 WebSocket 接收即時更新，並將這些狀態提供給各個 Vue 元件使用。

- **與後端通訊**:
    - **REST API**: 前端透過 Axios 向後端發送 HTTP 請求，以執行獲取任務列表、建立新任務等操作。
    - **WebSocket**: 為了實現即時更新，前端會建立一個到後端 `/api/ws` 的 WebSocket 連線，用於接收任務狀態（如：進行中、已完成、失敗）的即時變更通知。

- **建置流程**:
    - 開發者需在 `vue-app/` 目錄下執行 `bun install` 和 `bun run build`。
    - 建置後的靜態檔案（HTML, CSS, JS）會被輸出到 `vue-app/dist/` 目錄。
    - 後端 FastAPI 伺服器被設定為直接從該目錄提供前端應用服務，從而實現了單一服務的部署模式。

---

## 3. 後端架構 (Backend Architecture)

後端是一個基於 **FastAPI** 的 Python 應用，負責所有核心業務邏輯。

- **服務入口 (`src/api/api_server.py`)**:
    - 這是後端的主應用檔案，使用 `uvicorn` 運行。
    - 它定義了所有的 REST API 端點和 WebSocket 連線處理邏輯。
    - 同時，它也負責提供建置好的 Vue.js 前端靜態檔案。

- **資料庫層 (`src/db/`)**:
    - 資料庫的操作被抽象化，由兩個核心元件處理：
        - `manager.py`: 一個獨立的伺服器行程，作為資料庫的唯一寫入點，避免了多程序寫入 SQLite 時的鎖定問題。
        - `client.py`: 一個客戶端，供 `api_server.py` 和 `worker.py` 使用，透過 socket 與 `manager.py` 通訊，以安全地執行資料庫操作。

- **非同步任務 (`src/tasks/worker.py`)**:
    - 這是一個獨立的背景 Worker 程序。
    - 它會定期從資料庫中拉取待處理的任務（例如：音訊轉錄、影片下載），執行耗時的操作，並將結果寫回資料庫。
    - 在測試環境中，此 Worker 的功能會被模擬，以避免安裝大型依賴。

---

## 4. 測試架構 (Testing Architecture)

本專案的品質由一個位於 `e2e_tests/` 的端對端測試套件來保證。

- **核心技術棧**:
    - **測試框架**: Pytest
    - **瀏覽器自動化**: Playwright
    - **整合**: `pytest-playwright`

- **伺服器生命週期管理 (`conftest.py`)**:
    - 這是測試架構的**核心**。`conftest.py` 中定義了一個名為 `live_server` 的 `session` 級別 fixture。
    - **自動化流程**: 當執行測試時，此 fixture 會自動：
        1.  建置 Vue.js 前端。
        2.  啟動 `db_manager.py` 和 `api_server.py` 服務。
        3.  等待伺服器健康檢查通過。
        4.  將可用的伺服器 URL 提供給測試案例。
        5.  在所有測試結束後，自動、乾淨地關閉所有伺服器行程。
    - **優點**: 這種模式完全移除了手動啟動/關閉伺服器的需求，並透過動態尋找可用埠號和等待健康檢查，極大地提升了測試的穩定性和可靠性。

- **資料庫 Fixture (`db_client_fixture`)**:
    - `conftest.py` 同時也提供了一個 `db_client_fixture`。
    - 它依賴於 `live_server`，確保在伺服器完全啟動後，才為測試案例提供一個可用的資料庫客戶端實例，從而避免了競爭條件。

- **測試執行 (`runner/localtest.py`)**:
    - 為了方便執行，專案提供了一個入口腳本 `runner/localtest.py`。
    - 此腳本封裝了執行 `pytest` 的所有必要步驟，為開發者提供了一個單一的指令來運行完整的測試套件。
