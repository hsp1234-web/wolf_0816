# 鳳凰音訊轉錄儀 (Phoenix Transcriber)

[![zh-Hant](https://img.shields.io/badge/language-繁體中文-blue.svg)](README.md)

這是一個高效、可擴展的音訊轉錄專案，旨在提供一個可以透過 Web 介面輕鬆操作的語音轉文字服務。專案前端已由**Vue.js**驅動，後端整合了 **YouTube 影片處理與 AI 分析** 功能。

---

## 📚 文件中心

本專案的所有詳細技術文件，包括架構決策、開發者指南和研究報告，均已整理至 **[`DOC/`](./DOC/)** 資料夾中。我們建議所有開發者在開始工作前先閱讀以下核心文件：

*   **給 AI 開發者的說明 (`DOC/AGENTS.md`)**: 包含如何設定、測試和貢獻的必要指令。
*   **前端架構選型報告 (`DOC/FRONTEND_REFACTOR_OPTIONS.md`)**: 分析了專案前端的未來發展方向。
*   **初始架構研究 (`DOC/ARCHITECTURE_RESEARCH.md`)**: 記錄了專案初期的後端架構設計思路。

---

## ⚡️ 開發與執行指南 (Development and Execution Guide)

隨著「預先烘烤依賴」策略的成功實施，專案的啟動與開發流程已大幅簡化。舊的 `runner/` 目錄下的腳本已被廢棄。

### 一、首次設定或更新依賴

所有 Python 依賴項現在都被統一管理在一個壓縮檔中。當您首次設定專案，或在 `requirements-unified.txt` 中新增、刪除、更新了任何套件後，您**必須**執行以下指令來重新產生依賴包：

```bash
# 此指令會讀取 requirements-unified.txt，並將所有依賴打包成 dependencies.tar.gz
bash scripts/bake_dependencies.sh
```
**注意**：此步驟僅在依賴變更後才需執行。在日常開發中，如果沒有變更依賴，則無需重複執行。

### 二、啟動應用程式

我們現在有了一個統一的智慧啟動器。要啟動後端伺服器，只需執行：

```bash
# 此指令會自動解壓縮依賴並啟動伺服器
python run.py
```
伺服器將會啟動在 `http://127.0.0.1:8000`。

### 三、執行自動化測試

本專案使用 `pytest` 進行測試。得益於 `conftest.py` 中的全域 fixture，測試環境會被自動準備妥當（包括依賴的烘烤與注入）。

要執行完整的後端測試套件，只需在專案根目錄執行：
```bash
# 在執行前，請確保測試框架本身已安裝
# (只需執行一次：pip install pytest fastapi httpx)
pytest
```

---

## 📈 專案狀態

**核心功能與啟動器 - ✅ 已完成**

*   [x] **架構重構**：已完成穩定的多程序架構（協調器、資料庫管理器、API 伺服器）。
*   [x] **前端遷移**：已成功將前端從單一 HTML 檔案遷移至 Vue.js 單頁應用。
*   [x] **功能完整**：本地檔案轉錄與 YouTube 影片處理功能均已完整實現。
*   [x] **前端錯誤修復**：修復了任務標題無法正確顯示，以及檔名包含特殊字元時預覽失敗的問題。
*   [x] **本地啟動器**：提供穩定的本地服務啟動器 (`runner/localrun.py`) 與測試執行器 (`runner/localtest.py`)。
*   [x] **E2E 測試增強**：已修復並增強了基於 Playwright 的端對端測試，並透過共享的 fixture (`conftest.py`) 實現了伺服器生命週期的自動化管理。

---
## 📁 檔案結構

```
.
├── DOC/
│   ├── AGENTS.md                       # (重要) 給 AI 開發者的說明文件
│   └── ...                             # 其他歷史文件
├── scripts/
│   └── bake_dependencies.sh            # (重要) 用於烘烤依賴的腳本
├── src/                                # 主要後端應用程式原始碼
│   ├── core/
│   │   └── mini_server.py              # 應用程式主伺服器
│   └── ...
├── vue-app/                            # Vue.js 前端應用程式原始碼
│   ├── dist/                           # 前端建置後的產出目錄
│   └── ...
├── conftest.py                         # (重要) Pytest Fixture，用於準備測試環境
├── run.py                              # (重要) 唯一的應用程式啟動器
├── test_api_service.py                 # 主要的後端整合測試
├── requirements-unified.txt            # 專案所有 Python 依賴
├── .gitignore
└── README.md                           # 專案主說明文件
```
