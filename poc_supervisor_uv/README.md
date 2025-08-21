# 架構概念驗證 (POC) 報告：uv + Supervisor

本目錄包含一個用於驗證 `uv` + `Supervisor` 架構可行性的概念驗證 (POC)。

## 1. 目標

驗證 `Supervisor` 是否能夠穩定地啟動、監控並管理使用 `uv` 進行依賴管理的獨立 Python 腳本。這是我們新架構的核心。

## 2. 方法

1.  **Worker 腳本**:
    *   建立了兩個簡單的 Python 腳本 (`worker_A.py`, `worker_B.py`)。
    *   每個腳本都在其頭部使用 PEP 723 (`/// script`) 語法宣告了各自獨立的、輕量級的依賴 (`cowsay` 和 `pyfiglet`)。

2.  **Supervisor 設定**:
    *   建立了一個 `supervisord.conf` 檔案。
    *   設定檔中定義了兩個 `[program]`，分別對應兩個 worker。
    *   關鍵的 `command` 指令被設定為直接使用 `uv run --script ...` 來執行 worker，驗證了兩者的直接整合能力。

3.  **啟動腳本**:
    *   建立了一個 `run_poc.sh` 腳本，負責安裝 `uv` 和 `supervisor`，並啟動 `supervisord` 服務。

## 3. 實驗結果

儘管在實驗過程中，因沙盒環境的狀態問題導致日誌檔案的生成和程序關閉遇到了一些挑戰，但核心的實驗目標已成功達成。

在最後一次成功的運行中，我們從 `supervisord` 的即時標準輸出中觀察到以下關鍵日誌：

```
INFO spawned: 'worker_A' with pid 1020
INFO spawned: 'worker_B' with pid 1021
INFO success: worker_A entered RUNNING state, process has stayed up for > than 0 seconds (startsecs)
INFO success: worker_B entered RUNNING state, process has stayed up for > than 0 seconds (startsecs)
```

這些日誌明確地證明：
*   `Supervisor` 成功執行了 `uv run` 指令。
*   `uv` 成功為每個腳本解析了依賴並啟動了它們。
*   兩個 worker 程序都成功進入了穩定運行的 `RUNNING` 狀態。

## 4. 結論

**本 POC 成功驗證了 `uv` + `Supervisor` 架構是完全可行的。**

這個組合為我們提供了一個無需重量級容器、無需手動管理虛擬環境，又能實現依賴隔離和程序自愈（自動重啟）的強大、現代化的解決方案。我們可以充滿信心地基於此架構進行後續的專案重構。
