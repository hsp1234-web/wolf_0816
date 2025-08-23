# 系統架構與核心流程

本文件旨在說明當前系統的架構設計，特別是圍繞「任務池」批次處理模型的核心互動流程。

## 1. 核心理念：任務池 (Task Pool)

為了提供更具彈性且高效的使用者體驗，系統的核心互動模式已從「即時觸發」重構為「批次處理」。使用者在前端進行的多個操作（如上傳檔案、輸入 YouTube 連結）不會立即發送到後端，而是先被收集到一個統一的「任務池」中。

使用者可以預覽、管理這個任務池，並在準備就緒後，點擊一次「提交」按鈕，將整個任務佇列作為一個批次任務發送到後端。

## 2. 前端架構 (`vue-app`)

前端是一個基於 Vue.js 3 (Composition API) 和 Vite 的單頁應用程式 (SPA)。

- **狀態管理**: 使用 Pinia (`stores/tasks.js`) 進行全域狀態管理。
    - `taskPool`: 一個新的 state，用於存放使用者加入的待處理任務陣列。
    - `addTaskToPool`, `removeTaskFromPool`, `clearTaskPool`: 用於管理任務池的 actions。
    - `submitTaskPool`: 核心的 action，負責將 `taskPool` 中的任務打包並發送到後端的批次 API。

- **核心元件**:
    - `TaskUploader.vue`: 負責處理本地檔案上傳。其「新增」按鈕會觸發檔案預存 (staging) 流程，並將帶有 `file_id` 的任務新增至 `taskPool`。
    - `YouTubeReporter.vue`: 負責處理 YouTube 連結。其「新增」按鈕會將 YouTube 相關任務直接新增至 `taskPool`。
    - `TaskPool.vue`: 新的 UI 元件，用於視覺化展示 `taskPool` 的內容，並提供「提交全部」和「全部清除」的操作。
    - `App.vue`: 應用程式的主入口，整合了上述所有元件。

- **即時更新**: 系統狀態（如進行中、已完成的任務）由後端透過 WebSocket (`/ws`) 即時推送給前端，前端接收到訊息後更新 Pinia 狀態，從而響應式地更新 UI。

## 3. 後端架構 (`services/api_gateway`)

後端是基於 FastAPI 的 API 服務，作為所有請求的統一入口。

- **批次處理流程**:
    1.  **檔案預存 (File Staging)**:
        - `POST /api/stage-file`: 為了處理檔案上傳，前端會先呼叫此 API。API 會接收檔案，將其儲存到伺服器的一個臨時目錄 (`/staged_files`)，並回傳一個唯一的 `file_id`。
    2.  **批次提交 (Batch Submission)**:
        - `POST /api/batch-tasks`: 這是新的核心 API。它接收一個包含多個任務物件的 JSON 陣列。每個任務物件都描述了任務類型 (`transcription` 或 `youtube`) 及對應的 payload (包含 `file_id` 或 YouTube 網址等資訊)。
    3.  **任務分派 (Task Dispatching)**:
        - API 內部會遍歷任務陣列。
        - 根據任務類型，將任務分派給對應的背景工作者進行處理。此過程透過 **Huey** 任務佇列實現，確保了處理的非同步性和可靠性。

- **非同步任務處理**:
    - 使用 `Huey` 作為任務佇列的中介。當 API 收到請求後，它僅是快速地將一個「任務」登錄到 Huey 中，然後立刻回傳給使用者，告知任務已排入佇列。
    - 實際的耗時操作（如下載、轉錄、分析）由獨立的 **Huey Consumer** 程序在背景非同步執行。

- **啟動流程**:
    - 整個應用程式由根目錄的 `run_app.py` 啟動。
    - `run_e2e_test.py` 則是用於啟動測試環境的專用腳本。

這個架構將前端的互動與後端的處理有效解耦，提高了系統的響應速度、可靠性和可擴展性。
