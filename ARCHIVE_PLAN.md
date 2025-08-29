# 專案封存計畫 (ARCHIVE_PLAN)

根據作戰藍圖 754-A 的指示，在成功將輕量化後端 (`api_server_v2.py`) 與前端 (`index.html`) 整合進 `Colabpro.py` 啟動器後，以下是為簡化專案結構而建議封存或刪除的檔案與目錄清單。

此計畫旨在移除所有與舊版架構相關、現已不再使用的元件。

---

## 核心後端與服務 (Core Backend & Services)

以下是舊版後端的核心元件，應被完整移除。

- **`src/`**: 整個舊版後端原始碼目錄。
    - `api_server.py`: 舊版 FastAPI 伺服器。
    - `db/`: 舊版資料庫管理器。
    - `api/`, `core/`, `prompts/`, `tasks/`, `tools/`: 舊版後端的支援模組。
    - `requirements_light.txt`: 舊版後端的依賴文件。
- **`services/`**: 舊版的微服務目錄，由 `run_services.py` 啟動。
- **`workers/`**: 舊版的背景工作者目錄。
- **`scripts/run_services.py`**: 舊版的服務總管，已被 `Colabpro.py` 中的 `uvicorn` 指令取代。

## 前端 (Frontend)

- **`vue-app/`**: 整個舊版的 Vue.js 前端專案。其功能已被根目錄下的 `index.html` 取代。

## 依賴與設定檔 (Dependencies & Configs)

以下是與舊版架構相關的依賴與設定檔。

- `requirements-test-light.txt`
- `requirements-test.txt`
- `requirements-unified.txt`
- `bun.lock`, `package-lock.json`, `package.json`, `packages/`: 這些與舊的 `vue-app` 或其他 NodeJS 元件相關。

## 測試檔案 (Test Files)

以下測試檔案是針對舊架構編寫的，在新架構下已失效，應予以移除或重寫。

- `e2e_test.py`
- `test_api_gateway_ws.py`
- `test_cpu_torch_install.py`
- `test_lightweight_ai_poc.py`
- `test_new_architecture.py`
- `test_websocket_connection.py`

---

**建議操作：**
在指揮官批准後，可將上述所有項目移動至 `archive/` 目錄中進行封存，或直接刪除。
