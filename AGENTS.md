# AI 代理開發準則

本文件概述了開發與測試此專案的具體要求和限制。所有在此儲存庫中工作的 AI 代理都必須遵守這些準則。

---

## 1. 語言與溝通要求 (Language and Communication)

**❗❗❗ 極度重要 (CRITICAL) ❗❗❗**

**全程必須使用「繁體中文」進行溝通。**

這包括但不限於：
*   **使用者訊息**：所有與使用者的互動和回覆。
*   **程式碼註解**：所有新撰寫或修改的程式碼註解。
*   **提交訊息**：Git 的提交標題和內文。
*   **技術文件**：所有 `.md` 檔案的更新。
*   **日誌與輸出**：在不影響程式運作的前提下的所有輸出訊息。

此要求是專案的最高優先級之一，請務必遵守。

---

## 2. 開發目標 (Development Goal)

主要的開發目標是修復所有功能缺陷，並確保前後端能正確整合。核心的參考依據是 `api_server_old.py` 的後端邏輯以及 `vue-app/` 的前端結構。

---

## 3. 測試與依賴策略 (Testing and Dependency Strategy)

- **強制模擬 (Mocking is Mandatory)**: 所有重量級的外部依賴都必須被模擬。由於系統環境資源有限（磁碟空間、記憶體），**嚴格禁止**安裝或使用大型依賴。代理必須識別並模擬這些套件的功能。

- **需模擬的特定套件**: 根據 `requirements-worker.txt`，以下套件**絕不能**被安裝：
  - `torch`
  - `faster-whisper`
  - `google-generativeai`
  - `yt-dlp`
  - `pydub`
  - `WeasyPrint`

---

## 4. 測試執行 (Running Tests)

本專案採用了整合的測試執行流程，由 Pytest 和 Playwright 驅動。

### 4.1. 前端建置是前置步驟

**關鍵：** 在執行任何測試之前，Vue.js 前端應用**必須**被建置。後端伺服器會從 `vue-app/dist` 目錄提供靜態檔案，而此目錄僅在建置後才會生成。

建置指令（於專案根目錄執行）：
```bash
cd vue-app
bun install
bun run build
cd ..
```
> **注意：** `runner/localtest.py` 和 `e2e_tests/conftest.py` 中的測試啟動器會自動執行此建置步驟。

### 4.2. 標準測試執行方式

執行完整的自動化測試套件，請使用 `runner/localtest.py` 腳本。

```bash
python runner/localtest.py
```
此腳本會處理所有依賴安裝、前端建置、服務啟動、測試執行，並在結束後自動清理所有程序。它還內建了 **100 秒的超時機制**，以防止殭屍行程。

### 4.3. 基於 Fixture 的測試架構

E2E 測試 (`e2e_tests/`) 已全面重構，使用 Pytest Fixture (`conftest.py`) 來管理伺服器生命週期。這提供了更穩健、更可靠的測試環境。在撰寫新的 E2E 測試時，應優先使用 `live_server` 和 `db_client_fixture` 等共享的 Fixture。

---



## 5. 程式碼庫歷史背景 (Codebase Context)

- **問題起源**: 專案最初是從一個單一的靜態前端檔案 (`src/static/mp3.html`) 遷移到一個現代化的 Vue.js 應用 (`vue-app/`)。
- **核心問題**: 在遷移過程中，主要的後端檔案 `src/api/api_server.py` 被意外地簡化，遺失了大量關鍵功能，這是導致許多錯誤的根本原因。
- **解決方案**: 核心的修復工作是將 `api_server_old.py` 中的完整邏輯合併回 `src/api/api_server.py`，同時小心地保留服務 Vue.js 應用所需的新邏輯。這項工作已經完成。



請使用繁體中文計畫全程使用繁體中文進行溝通。 最終產出的 GitHub 敘述文件、程式碼註解及輸出訊息，在不影響程式運作的前提下，都要是繁體中文。
