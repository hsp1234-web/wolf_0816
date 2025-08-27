# -*- coding: utf-8 -*-
"""
善狼專案 - 門面伺服器 (Facade Server)

核心職責：
1.  **立即啟動**：此伺服器應在幾秒內啟動，不執行任何耗時操作。
2.  **提供前端**：提供 Vue.js 單頁應用 (SPA) 的靜態檔案。
3.  **啟動背景安裝**：在背景啟動 `background_installer.py` 腳本來處理重量級依賴。
4.  **進度回報**：建立 WebSocket 端點，即時轉發背景安裝腳本的進度給前端。
"""
import asyncio
import subprocess
import os
import sys
import json
import httpx
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse
from typing import List, Dict, Any
from fastapi.middleware.cors import CORSMiddleware

# --- 全局變數與設定 ---

# 用於儲存所有活躍的 WebSocket 連接
active_connections: List[WebSocket] = []

# 專案根目錄的絕對路徑
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 背景安裝腳本的路徑
installer_script_path = os.path.join(project_root, "src", "background_installer.py")

# Vue App 靜態檔案的路徑
vue_app_dist_path = os.path.join(project_root, "vue-app", "dist")

# --- FastAPI 應用實例 ---
app = FastAPI(title="門面伺服器", description="提供前端介面並管理背景依賴安裝")

# --- CORS 中介軟體設定 ---
# 這是修復 WebSocket 403 Forbidden 錯誤的關鍵
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源，用於測試和 Colab 環境
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 背景任務 ---

async def broadcast_json(message: Dict[str, Any]):
    """將 JSON 訊息廣播給所有連接中的客戶端"""
    message_str = json.dumps(message, ensure_ascii=False)
    for connection in active_connections:
        await connection.send_text(message_str)

async def run_installer_and_broadcast():
    """在背景執行安裝腳本，並將其標準輸出/錯誤即時廣播出去"""
    await broadcast_json({"type": "log", "data": "伺服器：準備開始安裝依賴..."})

    # 檢查是否需要以 "輕量模式" 啟動 (透過環境變數)
    installer_args = [sys.executable, installer_script_path]
    if os.environ.get("LIGHT_MODE") == "1":
        installer_args.append("--light-mode")
        await broadcast_json({"type": "log", "data": "伺服器：已偵測到輕量模式(LIGHT_MODE=1)，將以輕量模式進行安裝。"})
    else:
        await broadcast_json({"type": "log", "data": "伺服器：將以標準模式進行安裝。"})


    process = await asyncio.create_subprocess_exec(
        *installer_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # 異步讀取 stdout 和 stderr
    while process.returncode is None:
        # 修正：將協程包裝成任務
        stdout_task = asyncio.create_task(process.stdout.readline())
        stderr_task = asyncio.create_task(process.stderr.readline())

        done, pending = await asyncio.wait(
            {stdout_task, stderr_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in done:
            line_bytes = task.result()
            if line_bytes:
                line = line_bytes.decode('utf-8', errors='replace').strip()
                if line: # 確保不廣播空行
                    await broadcast_json({"type": "log", "data": line})

        # 取消未完成的任務，避免資源洩漏
        for task in pending:
            task.cancel()

        # 短暫休眠以避免CPU空轉
        await asyncio.sleep(0.1)

    # 確保所有剩餘的輸出都被讀取
    stdout, stderr = await process.communicate()
    if stdout:
        # 將可能的多行輸出拆分後逐行發送
        for line in stdout.decode('utf-8', errors='replace').strip().split('\n'):
            if line:
                await broadcast_json({"type": "log", "data": line})
    if stderr:
        for line in stderr.decode('utf-8', errors='replace').strip().split('\n'):
            if line:
                await broadcast_json({"type": "error", "data": f"錯誤：{line}"})


    if process.returncode == 0:
        await broadcast_json({"type": "log", "data": "伺服器：安裝程序成功結束，正在確認主服務狀態..."})
        main_server_ready = await probe_main_server(timeout=60)
        if main_server_ready:
            await broadcast_json({"type": "log", "data": "伺服器：主服務已上線！"})
            await broadcast_json({"type": "status", "data": "INSTALLATION_COMPLETE"})
        else:
            await broadcast_json({"type": "error", "data": "伺服器：主服務探測超時，未能確認其成功啟動。"})
            await broadcast_json({"type": "status", "data": "INSTALLATION_FAILED"})
    else:
        await broadcast_json({"type": "error", "data": f"伺服器：安裝過程發生錯誤，返回碼：{process.returncode}"})
        await broadcast_json({"type": "status", "data": "INSTALLATION_FAILED"})

async def probe_main_server(timeout: int) -> bool:
    """
    在指定超時時間內，探測主 API 服務是否已在 8008 埠上線。
    我們只探測根路徑，因為主服務啟動後，即使 API 路由尚未完全就緒，
    HTTP 伺服器本身也會回應請求 (即使是 404)。
    """
    start_time = time.time()
    url = "http://127.0.0.1:8008/"
    async with httpx.AsyncClient() as client:
        while time.time() - start_time < timeout:
            try:
                response = await client.get(url, timeout=2)
                # 任何來自伺服器的回應 (即使是 404 或 500) 都表示 HTTP 服務已上線
                await broadcast_json({"type": "log", "data": f"探測到主服務回應: {response.status_code}"})
                return True
            except httpx.RequestError as e:
                await broadcast_json({"type": "log", "data": f"探測主服務中... (錯誤: {type(e).__name__})"})
                await asyncio.sleep(1)
    return False

@app.on_event("startup")
async def startup_event():
    """伺服器啟動時，在背景異步執行安裝任務"""
    asyncio.create_task(run_installer_and_broadcast())


# --- WebSocket 端點 ---

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """處理 WebSocket 連接，用於即時狀態更新"""
    # [斷點日誌] 增加日誌以追蹤連線過程
    print("[Breakpoint] /ws/status: 收到一個新的 WebSocket 連線請求。")
    await websocket.accept()
    print("[Breakpoint] /ws/status: WebSocket 連線已接受。")
    active_connections.append(websocket)
    try:
        # 歡迎訊息
        welcome_message = {"type": "status", "data": "伺服器：連接成功！正在等待依賴安裝進度..."}
        await websocket.send_text(json.dumps(welcome_message, ensure_ascii=False))
        print("[Breakpoint] /ws/status: 已發送歡迎訊息。")
        # 保持連接開啟，以接收來自服務端的廣播
        while True:
            await websocket.receive_text() # 等待客戶端可能發送的訊息 (雖然目前不會處理)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print("[Breakpoint] /ws/status: 一個客戶端已斷開連接。")


# --- 靜態檔案服務 (SPA) ---
# 根據 CH_log.md 中的歷史經驗 (2025-08-25T07:40:38+08:00),
# 為了完全避免根路徑掛載與 WebSocket 的潛在衝突，並適應前端資源的固定路徑，
# 我們將靜態檔案掛載到 /ui 子路徑下，並在根目錄 / 提供一個自動重定向。

@app.get("/", include_in_schema=False)
async def root_redirect():
    """在根目錄提供到 /ui/ 的重定向"""
    return RedirectResponse("/ui/")

# 將包含 SPA 的靜態檔案目錄掛載到 /ui
# html=True 確保了所有指向 /ui 下不存在路徑的請求都會回傳 index.html
app.mount("/ui", StaticFiles(directory=vue_app_dist_path, html=True), name="ui")


# --- 主程式入口 (用於直接執行測試) ---
if __name__ == "__main__":
    import uvicorn
    print(f"靜態檔案目錄: {vue_app_dist_path}")
    print(f"安裝腳本: {installer_script_path}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
