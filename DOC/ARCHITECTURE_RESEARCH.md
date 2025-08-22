# 系統架構現況分析

## 系統架構圖 (v6 - 動態工作者與隔離環境)

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

    subgraph "動態工作者管理器"
        SM[啟動管理者<br>run_startup_manager_worker.py]
    end

    subgraph "獨立工作者 (由管理者動態啟動)"
        W_YT[YouTube 工作者<br>run_youtube_worker.py<br>(.venv-youtube)]
        W_TS[轉錄工作者<br>run_transcription_worker.py<br>(.venv-transcription)]
        W_AI[AI 報告工作者<br>run_ai_report_worker.py<br>(.venv-ai-report)]
    end

    subgraph "開發與測試"
        F[測試套件<br>(test.py)]
        G[開發啟動器<br>(runner/localrun_new.py)]
    end

    A -- "REST API / WebSocket" --> B
    B -- "寫入任務" --> D
    D -- "讀/寫" --> E

    %% Startup Manager monitors the DB
    SM -- "輪詢任務" --> D

    %% Startup Manager launches workers
    SM -.-> |偵測到 'youtube_download' 任務| W_YT
    SM -.-> |偵測到 'transcription' 任務| W_TS
    SM -.-> |偵測到 'ai_report' 任務| W_AI

    %% Workers interact with the DB
    W_YT -- "讀/寫任務" --> D
    W_TS -- "讀/寫任務" --> D
    W_AI -- "讀/寫任務" --> D

    %% Launcher starts only core services
    G -- "啟動" --> B
    G -- "啟動" --> D
    G -- "啟動" --> SM
```

**文件更新日期：** 2025年8月19日
**作者:** Jules (AI Software Engineer)
**狀態:** **v6 - 動態工作者架構**

---

## 1. 摘要 (Executive Summary)

為了最佳化啟動時間和資源利用率，系統架構已從 v5 的「多工作者」模式，演進為 **v6 的「動態工作者與隔離環境」模式**。

此架構的核心變更是引入了一個新的**智慧型「啟動管理者」(`run_startup_manager_worker.py`)**。主應用程式在啟動時，只會載入最核心的服務（前端、API、資料庫管理器）和這個啟動管理者。

其他執行耗時任務的**工作者（YouTube、轉錄、AI）不再隨主應用一同啟動**。相反，它們會在系統偵測到需要其處理的任務時，由「啟動管理者」**動態地、按需地**啟動。

更重要的是，**每一個工作者都在其專屬的、完全隔離的 Python 虛擬環境中運行**，徹底杜絕了依賴衝突的風險。

---

## 2. 前端架構 (Frontend Architecture)

前端架構保持不變，仍然是一個基於 **Vue.js 3** 的單頁應用程式（SPA）。

- **與後端通訊**: 使用者透過前端介面提交任務（例如輸入 YouTube 網址），前端會呼叫後端 API。後端將任務以 `pending` 狀態存入資料庫。使用者幾乎可以立即在介面上看到任務已進入佇列，實現了極佳的響應體驗。

---

## 3. 後端架構 (v6)

### 3.1. 核心服務

核心服務的角色更加純粹，只負責最關鍵的即時互動：
- **API 伺服器 (`src/api/api_server.py`)**: 接收使用者請求，將任務寫入資料庫。
- **資料庫管理器 (`src/db/manager.py`)**: 管理對 SQLite 資料庫的存取。

### 3.2. 動態工作者架構 (v6 核心變更)

這是新架構的核心。

- **啟動管理者 (`run_startup_manager_worker.py`)**:
    - 這是唯一一個會隨核心服務一同啟動的特殊工作者。
    - 它的職責是：
        1.  **持續監控**資料庫中的任務佇列。
        2.  當偵測到一個 `pending` 狀態的任務時，檢查該任務類型（如 `transcription`）所需的工作者是否已在運行。
        3.  如果工作者不在運行，它會**動態地啟動**對應的工作者程序（如 `run_transcription_worker.py`）。

- **隔離的虛擬環境 (Isolated Virtual Environments)**:
    - 「啟動管理者」在首次啟動某個工作者前，會為其建立一個專屬的 Python 虛擬環境（例如，為轉錄工作者建立 `.venv-transcription`）。
    - 接著，它會使用 `uv` 在該環境中安裝**僅該工作者需要**的依賴（來自 `requirements-transcription.txt`）。
    - **優點**: 提供了極致的穩定性和依賴隔離。
    - **權衡**: 使用者提交的**第一筆**特定類型的任務，會有一次性的啟動延遲（用於建立環境和安裝依賴）。但此後的同類型任務將會被立即處理。

---

## 4. 測試與開發環境 (v6)

### 4.1. 測試架構 (`test.py`)

測試腳本 (`test.py`) 已被重構，以完全支援新架構。
- 它現在透過執行 `runner/localrun_new.py` 來啟動服務，確保了測試與開發環境的一致性。
- 由於主啟動器現在極為迅速，`test.py` 可以快速驗證核心服務的可用性和前端介面的載入。

### 4.2. 開發環境啟動流程 (`runner/localrun_new.py`)

開發啟動器 (`runner/localrun_new.py`) 的職責已被**大幅簡化**：
- **依賴安裝**: 它現在只負責安裝核心服務的依賴 (`requirements-server.txt`)。所有工作者的依賴都交由「啟動管理者」動態處理。
- **服務啟動**: 它只會啟動三個程序：
    1.  資料庫管理器 (`src/db/manager.py`)
    2.  API 伺服器 (`src/api/api_server.py`)
    3.  **啟動管理者 (`run_startup_manager_worker.py`)**
- **結論**: 這個流程確保了開發者可以在**極短的時間內（目標為 30 秒內）**獲得一個可用的前端介面來提交任務，實現了最佳的開發體驗。

---

## 5. 主要依賴套件與資源分析 (已過時)

**本節內容已過時**。

原先的分析是基於一個統一的 `requirements-worker.txt` 檔案。在新架構 (v6) 下，這些依賴已被拆分到各自的檔案中 (`requirements-youtube.txt`, `requirements-transcription.txt` 等)，並在隔離的虛擬環境中進行管理。資源消耗最高的套件（如 `torch`）只會在需要執行轉錄任務時，才會被安裝和載入到其專屬的環境中。
