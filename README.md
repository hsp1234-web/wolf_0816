# 鳳凰音訊轉錄儀 (Phoenix Transcriber)

[![zh-Hant](https://img.shields.io/badge/language-繁體中文-blue.svg)](README.md)

這是一個高效、可擴展的音訊轉錄專案，旨在提供一個可以透過 Web 介面輕鬆操作的語音轉文字服務。專案近期已整合 **YouTube 影片處理與 AI 分析** 功能。

---

## 📚 文件中心

本專案的所有詳細技術文件，包括架構決策、開發者指南和研究報告，均已整理至 **[`DOC/`](./DOC/)** 資料夾中。我們建議所有開發者在開始工作前先閱讀以下核心文件：

*   **給 AI 開發者的說明 (`DOC/AGENTS.md`)**: 包含如何設定、測試和貢獻的必要指令。
*   **前端架構選型報告 (`DOC/FRONTEND_REFACTOR_OPTIONS.md`)**: 分析了專案前端的未來發展方向。
*   **初始架構研究 (`DOC/ARCHITECTURE_RESEARCH.md`)**: 記錄了專案初期的後端架構設計思路。

---

## ⚡️ 如何啟動與測試

我們提供多種執行方式，請根據您的需求選擇。

### 方式一：本地開發與驗證 (建議)

這是最推薦的入門與驗證方式。單一指令即可完成所有環境設定並執行一次輕量級的快照測試，以確認系統是否正常運作。

**此方式適用於**：
*   首次設定開發環境。
*   快速驗證核心環境（Python, Node.js, 服務啟動）是否配置正確。

**如何使用**:
```bash
# 執行此指令將會自動安裝所有依賴、啟動伺服器、擷取快照，然後關閉。
bun run snapshot
```
當腳本顯示「🎉 輕量級快照腳本執行成功！」時，即表示您的開發環境已準備就緒。詳細的說明請參閱 **[`DOC/AGENTS.md`](./DOC/AGENTS.md)**。

#### 測試策略 (Testing Strategy)

本專案的品質保證流程，優先採用**自動化斷言 (Automated Assertions)** 的方式來進行前端功能驗證，而非依賴視覺化截圖比對。我們強烈建議在 Playwright 測試腳本中，直接使用 `expect(locator)` 來驗證 UI 元素的狀態（如可見性、文字內容、屬性等）。

---

### 方式二：手動啟動後端服務 (進階)

如果您需要一個**持續運行的後端服務**來進行前端開發或手動測試，請使用 `circus` 直接啟動。

**此方式適用於**：
*   本地端開啟 `src/static/mp3.html` 進行手動功能測試。
*   需要手動連接後端進行除錯的場景。

**注意**：此方式不會自動安裝依賴，請先執行一次 `bun run snapshot` 以確保環境完整。

**如何使用**:
```bash
# 啟動所有後端服務
python -m circus.circusd circus.ini

# 完成測試後，可使用以下指令關閉服務
python -m circus.circusctl quit
```
服務啟動後，您可以透過 `http://127.0.0.1:42649` 訪問前端介面。

---

## 📈 專案狀態

**核心功能與測試 - ✅ 已完成**

*   [x] **架構重構**：已完成穩定的多程序架構（協調器、資料庫管理器、API 伺服器）。
*   [x] **功能完整**：本地檔案轉錄與 YouTube 影片處理功能均已完整實現。
*   [x] **測試穩定**：`local_run.py` 後端整合測試與 `bun run snapshot` 環境驗證腳本運作正常。

---
## 📁 檔案結構

```
.
├── DOC/
│   ├── AGENTS.md                       # (重要) 給 AI 開發者的說明文件
│   ├── ARCHITECTURE_RESEARCH.md        # 初始後端架構研究
│   ├── FRONTEND_REFACTOR_OPTIONS.md    # 前端架構選型報告
│   └── bug.md                          # 歷史 Bug 分析
├── config/                             # 所有環境設定檔
├── e2e_tests/                          # 端對端測試
├── runner/                             # 任務啟動器腳本
├── src/                                # 主要應用程式原始碼
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── static/
│   ├── tasks/
│   └── tools/
├── .gitignore
├── package.json
├── pyproject.toml
└── README.md                           # 專案主說明文件
```
