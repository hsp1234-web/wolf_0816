---
**文件封存通知 (Document Archival Notice)**

**封存日期 (Archived on):** 2025-08-19T07:47:00Z
**原因 (Reason):** 這是一份早期的開發計畫，已被 `plan.md` 和 `DOC/ARCHITECTURE_RESEARCH.md` 中更新的 `Huey` + `SQLite` + `Circus` 架構決策所取代。內容僅供歷史參考。
(This is an early development plan that has been superseded by the updated `Huey` + `SQLite` + `Circus` architectural decision in `plan.md` and `DOC/ARCHITECTURE_RESEARCH.md`. This content is for historical reference only.)
---

好的，遵照您的指示。我們將完全按照您的決策來執行。以下是整合我們所有討論後，得到的一份清晰、統一的最終計畫。這將是我們接下來所有工作的指導方針。

**核心設計原則：**
*   **單一檔案，易於管理**：每個工作者都是一個獨立的 `.py` 檔案，所有設定（如超時、重試次數）都以註解形式寫在檔案頂部，方便直接修改。
*   **穩定性優先**：採用單線程處理模型，確保任務一個接一個執行，不出錯。首先追求整個流程跑通。
*   **邊界清晰**：每個工作者只負責一種類型的任務（例如 `youtube_worker` 只處理 YouTube 任務），保持架構的簡潔與單一職責。
*   **暫不實作進階功能**：心跳機制、系統級排程 (`cron`) 等功能，將保留給未來在 Colab 環境中實作，目前階段不予開發。

---

### **第一階段：概念驗證 (Proof of Concept) - 改造 YouTube 服務**

**目標：** 建立第一個符合我們新規範的「臨時工作者」，並驗證其可行性。

1.  **修改 `youtube_service` 的任務定義 (`tasks.py`)**
    *   **位置**: `services/youtube_service/tasks.py`
    *   **任務**: 為檔案中 `@huey.task()` 裝飾的函數增加錯誤處理機制。
    *   **修改內容**: 加入 `retries=3` 和 `retry_delay=30` 參數。這將使任何失敗的任務，在放棄前會每隔 30 秒重試一次，總共嘗試 3 次。

2.  **建立 `run_youtube_worker.py`**
    *   **位置**: 在專案的根目錄下建立此新檔案。
    *   **任務**: 編寫臨時工作者的主要執行邏輯。
    *   **程式碼結構**:
        *   在檔案頂部，使用註解區塊來放置設定檔。
            ```python
            # --- 設定區 (可直接在此修改) ---
            IDLE_TIMEOUT_SECONDS = 20 # 沒有任務後，等待 20 秒就自動關閉
            LOOP_SLEEP_SECONDS = 2   # 每 2 秒檢查一次佇列
            # --- 設定區結束 ---
            ```
        *   實現主迴圈邏輯：啟動、檢查任務、執行、閒置倒數、自動關閉。
        *   所有日誌和輸出訊息都使用繁體中文。

3.  **手動測試與驗證**
    *   **任務**: 執行 `python run_youtube_worker.py`。
    *   **驗證**:
        *   **正常流程**: 觸發一個 YouTube 任務，觀察日誌確認工作者是否成功接收、執行，並在閒置 20 秒後自動退出。
        *   **錯誤流程**: 模擬一個會失敗的任務，觀察日誌確認工作者是否確實執行了 3 次重試，每次間隔 30 秒。

### **第二階段：推廣至其他微服務**

**目標：** 將成功的模式複製到其他背景服務，完成架構的全面轉型。

4.  **改造 `transcription_service`**
    *   **修改任務定義**: 同步驟 1，在 `services/transcription_service/tasks.py` 中為任務加入重試機制。
    *   **建立工作者**: 複製 `run_youtube_worker.py` 為 `run_transcription_worker.py`，並修改其日誌訊息和引用的任務模組，使其專門處理轉錄任務。

5.  **改造 `ai_report_service`**
    *   **修改任務定義**: 同步驟 1，在 `services/ai_report_service/tasks.py` 中為任務加入重試機制。
    *   **建立工作者**: 複製 `run_youtube_worker.py` 為 `run_ai_report_worker.py`，並修改其日誌訊息和引用的任務模組，使其專門處理 AI 報告任務。

### **第三階段：文件與最終化**

**目標：** 確保專案的知識得以傳承，方便未來維護。

6.  **撰寫架構說明文件**
    *   **任務**: 在專案根目錄建立一份新的 `README.md` (如果已存在，則進行大幅更新)。
    *   **內容**:
        *   詳細說明「臨時工作者」的設計理念與運作方式。
        *   清楚列出如何啟動每一個工作者 (e.g., `python run_youtube_worker.py`)。
        *   提供一份簡易指南，說明未來若要新增一個新的工作者（例如 `image_processing_worker`），需要遵循哪些步驟。
        *   所有文件內容均使用繁體中文。

7.  **提交最終程式碼**
    *   **任務**: 當所有工作者都改造並測試完畢，且文件也撰寫完成後，我將提交所有變更。
