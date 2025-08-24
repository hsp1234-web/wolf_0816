# 架構重構與穩定性提升計畫書

**文件目的**: 本文件旨在深入分析當前專案架構中存在的、導致不穩定和開發流程困難的核心問題，並提出一套系統性的、可執行的重構方案。此方案將作為後續開發工作的指導藍圖。

---

## 1. 核心痛點分析

經過對 `CHANGELOG.md` 的詳細回顧和對系統行為的觀察，我們將問題根源歸納為以下兩大類：

### 1.1. Huey 背景任務系統的不穩定

所有與 Huey 相關的崩潰和不穩定，都源於兩個根本性的架構缺陷：

*   **架構耦合與混亂的導入鏈 (Architectural Coupling & Tangled Imports)**:
    *   **檔名衝突**: 專案自訂的 `huey_consumer.py` 腳本曾與 Huey 套件官方的執行檔同名，導致 Python 的導入系統產生無法預測的 `AttributeError`。
    *   **循環導入**: 主啟動腳本 (`run_app.py`)、Huey 入口 (`huey_entrypoint.py`) 與工作者模組 (`workers/*.py`) 之間形成了複雜的依賴閉環。主腳本需要匯入工作者來註冊任務，而工作者反過來又可能需要匯入主腳本中的 `huey` 實例，導致了啟動時的脆弱性。

*   **脆弱的程序管理 (Fragile Process Management)**:
    *   **不正確的啟動方式**: 我們曾使用 `python3 huey_consumer.py` 而非官方的 `huey_consumer.py ...` 來啟動，這影響了 Huey 的內部模組載入機制。
    *   **手動的時序控制**: 在 `run_app.py` 中，我們被迫使用 `time.sleep` 或探測檔案/網路埠的方式，來手動協調 Huey consumer 與其他服務（如 API Gateway）的啟動順序，這種方式極不可靠。

### 1.2. AI 模型管理的複雜性與僵化

*   **規格寫死在程式碼中**: 當前，所有 AI 模型（如 Whisper 的 `tiny`, `base`）的規格和參數都直接寫死在前後端的程式碼中。
*   **難以擴展**: 每當需要新增一個模型、調整其參數或更換提供商時，都需要修改多處程式碼，費時且容易出錯。
*   **與「分段啟動」目標衝突**: 僵化的模型管理方式，使得我們無法實現根據使用者選擇，來動態安裝對應依賴的進階功能。

---

## 2. 建議的重構方案

我們建議採取「**統一後端 + 模型註冊表**」的綜合策略，分階段解決上述所有問題。

### 方案一：統一後端架構，根除 Huey 不穩定性 (推薦)

**核心思想**: 不再將 Huey consumer 作為一個獨立的外部程序對待，而是將其**內建化**，作為一個背景執行緒在主應用程式中直接管理。

**具體作法**:

1.  **建立單一權威入口 (`main.py`)**:
    *   建立一個新的 `main.py`，它將是未來啟動整個後端的**唯一入口**。
    *   在此檔案中，我們安全地建立 `huey` 的實例，並匯入所有工作者模組 (`workers/*.py`) 以完成任務註冊。
    *   我們將不再使用 `subprocess` 去呼叫 `huey_consumer.py`。取而代之，我們將直接使用 Huey 官方提供的 `huey.create_consumer()` API 來建立一個 consumer 物件。
    *   將這個 consumer 物件放在一個獨立的背景執行緒 (`threading.Thread`) 中運行。

2.  **整合所有服務**:
    *   `DB Manager` 將被移除，其功能（資料庫初始化、連線管理）將被整合進 `main.py` 的 FastAPI `lifespan` 事件中。
    *   `run_app.py` 和 `runner/` 下的所有腳本將被**正式棄用**。

**預期成果**:
*   **消除所有導入問題**: 由於所有模組都在同一個程序和導入上下文中，檔名衝突和循環導入問題將不復存在。
*   **消除程序管理問題**: 不再有複雜的子程序管理、環境變數傳遞和時序問題。主程序完全掌控 consumer 的生命週期。
*   **架構極大簡化**: 開發者只需理解 `main.py` 這一個檔案，就能掌握整個後端的啟動邏輯。

### 方案二：建立「模型註冊表」，實現靈活的模型管理

**核心思想**: 將 AI 模型的規格定義，從程式碼中徹底抽離，變成一份結構化的外部設定檔。

**具體作法**:

1.  **建立 `models.json` 設定檔**:
    *   在專案根目錄建立 `models.json` 檔案。此檔案將成為 AI 模型的唯一「真相來源」。
    *   檔案結構如下：
        ```json
        {
          "transcription_models": [
            {
              "id": "tiny",
              "name": "Tiny (最快，通用)",
              "provider": "faster-whisper",
              "params": { "model_size": "tiny", "compute_type": "int8" },
              "requirements": ["torch", "faster-whisper"],
              "description": "適用於快速預覽和非關鍵任務。"
            },
            {
              "id": "large-v3",
              "name": "Large v3 (最準確)",
              "provider": "faster-whisper",
              "params": { "model_size": "large-v3", "compute_type": "float16" },
              "requirements": ["torch", "faster-whisper"],
              "description": "提供最高的轉錄準確率，但速度較慢。"
            }
          ],
          "youtube_report_models": [
            {
              "id": "gemini-1.5-flash",
              "name": "Gemini 1.5 Flash (推薦)",
              "provider": "google-gemini",
              "params": { "model_name": "gemini-1.5-flash-latest" },
              "requirements": ["google-generativeai"],
              "description": "速度與品質的絕佳平衡。"
            }
          ]
        }
        ```

2.  **後端與前端的互動**:
    *   後端在啟動時讀取此 `models.json`。
    *   前端透過一個專門的 API 端點來獲取這份模型列表。
    *   前端 UI 根據收到的列表，**動態渲染**出所有可用的模型選項，包括其名稱、描述等。

**預期成果**:
*   **極高的可擴展性**: 未來新增或修改模型，只需編輯 `models.json`，無需更動任何程式碼。
*   **職責清晰**: AI 模型的定義與應用程式的業務邏輯完全分離。
*   **為「分段啟動」奠定基礎**: `requirements` 欄位讓我們可以準確地知道每個模型需要哪些依賴，為後續實現依賴的延遲安裝提供了可能性。

### 方案三：實現「分段啟動」，優化使用者體驗

**核心思想**: 結合前兩個方案，讓輕量的 Web 服務先行，耗時的 AI 元件在背景準備。

**具體作法**:

1.  **分離依賴**:
    *   建立 `requirements-core.txt` (只包含 `fastapi` 等核心依賴) 和 `requirements-ai.txt` (包含 `torch` 等大型依賴)。
2.  **兩階段啟動**:
    *   主程序 `main.py` 啟動時，只安裝 `requirements-core.txt`，讓 Web 介面秒級可用。
    *   然後，使用 FastAPI 的 `BackgroundTasks` 功能，在背景執行 `uv pip install -r requirements-ai.txt`。
    *   同時透過 WebSocket 向前端回報安裝進度。
3.  **延遲載入 (Lazy Loading)**:
    *   在工作者任務函式**內部**才 `import torch` 和 `import faster_whisper`，確保只有在執行第一個任務時，才將模型載入記憶體。

---

## 3. 後端測試策略：為重構建立安全網

在進行任何大規模重構之前，建立一套穩健的、獨立於前端的後端測試策略至關重要。這能確保我們未來的每一次修改都有安全網保護。我們建議使用 `Pytest` 作為統一的測試框架，並採納以下分層策略：

### 第一層：單元測試 (Unit Tests) - 快速、隔離

*   **目標**：驗證單一函式或類別的內部邏輯是否正確，完全不涉及外部依賴（如資料庫、網路、檔案系統）。
*   **工具**：`Pytest` + `unittest.mock`。
*   **範例**：
    *   測試一個負責解析 YouTube 網址的函式，給它一個網址字串，斷言它是否能正確回傳影片 ID。
    *   測試一個負責計算任務優先級的演算法，給它不同的任務參數，斷言它是否回傳了正確的優先級數值。
*   **優點**：執行速度極快（毫秒級），結果穩定可靠，是 TDD (測試驅動開發) 的基石。我們應該為所有核心的、無副作用的業務邏輯撰寫單元測試。

### 第二層：服務級整合測試 (Service-level Integration Tests) - 驗證內部通訊

*   **目標**：在不啟動完整 Web 伺服器的情況下，驗證單一服務（如 `api_gateway`）的內部元件是否能協同工作。
*   **工具**：`Pytest` + `FastAPI` 的 `TestClient`。
*   **範例**：
    *   **測試 API 端點**：使用 `TestClient` 直接對我們的 FastAPI app 物件傳送模擬的 HTTP 請求。例如，`POST` 一個新任務到 `/api/transcribe`，然後斷言我們的資料庫中是否多了一筆對應的任務紀錄。
    *   **測試 WebSocket**：同樣地，`TestClient` 也支援測試 WebSocket 端點。我們可以模擬一個前端用戶端連線，發送 `FETCH_GEMINI_MODELS` 訊息，然後斷言收到的回應是否符合預期格式。
*   **優點**：比單元測試更全面，它測試了 API 的路由、請求驗證、依賴注入等真實邏輯，但又比啟動完整伺服器要快得多，且不需要處理網路埠衝突。

### 第三層：系統級整合測試 (System-level Integration Tests) - 驗證完整後端

*   **目標**：驗證**所有**後端服務（重構後的 FastAPI + Huey Consumer）之間真實的通訊鏈路是否通暢。
*   **工具**：`Pytest` + `pytest-xprocess` (或自訂的 `conftest.py` Fixture)。
*   **實現方式**：
    1.  **使用 `conftest.py` 建立 Fixture**：建立一個名為 `full_backend` 的 Pytest Fixture。
    2.  **在 Fixture 中啟動服務**：當測試需要這個 `full_backend` Fixture 時，它會自動在背景啟動我們統一後的 `main.py`。
    3.  **執行健康檢查**：Fixture 在啟動服務後，會執行一個迴圈來探測 API 的健康檢查端點，直到服務完全就緒，才將控制權交還給測試案例。
    4.  **自動清理**：測試結束後，Fixture 會自動終止所有背景服務，確保環境的乾淨。
*   **範例**：
    *   一個測試案例，首先呼叫 `/api/transcribe` 端點提交一個轉錄任務。
    *   然後，它會直接查詢 Huey 的佇列或我們的資料庫，斷言該任務是否已成功地被 `huey_consumer` 接收並開始處理。
    *   最後，它可以輪詢任務狀態的 API，斷言任務最終是否變為 `completed` 狀態。
*   **優點**：這是**最真實**的後端測試，它能發現由多服務互動所引發的所有問題。

---

## 4. 總結與路線圖

我們建議的路線圖是：
1.  **建立測試安全網**：優先實施第二層「服務級整合測試」，為現有 API 建立基本的保護。
2.  **執行核心重構**：採納**方案一**和**方案二**，即「**統一後端 + 模型註冊表**」。這將為我們打下一個穩定、可維護的架構基礎。
3.  **優化使用者體驗**：在穩定的新架構上，實施**方案三**「分段啟動」，最終實現一個既功能強大、又使用者體驗流暢的應用程式。
4.  **完善測試覆蓋**：在重構過程中，逐步補全第一層和第三層的測試。
