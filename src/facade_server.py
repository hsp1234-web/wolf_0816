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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
from typing import List

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


# --- 背景任務 ---

async def broadcast(message: str):
    """將訊息廣播給所有連接中的客戶端"""
    for connection in active_connections:
        await connection.send_text(message)

async def run_installer_and_broadcast():
    """在背景執行安裝腳本，並將其標準輸出/錯誤即時廣播出去"""
    await broadcast("伺服器：準備開始安裝依賴...")

    # 檢查是否需要以 "輕量模式" 啟動 (透過環境變數)
    installer_args = [sys.executable, installer_script_path]
    if os.environ.get("LIGHT_MODE") == "1":
        installer_args.append("--light-mode")
        await broadcast("伺服器：已偵測到輕量模式(LIGHT_MODE=1)，將以輕量模式進行安裝。")
    else:
        await broadcast("伺服器：將以標準模式進行安裝。")


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
                    await broadcast(line)

        # 取消未完成的任務，避免資源洩漏
        for task in pending:
            task.cancel()

        # 短暫休眠以避免CPU空轉
        await asyncio.sleep(0.1)

    # 確保所有剩餘的輸出都被讀取
    stdout, stderr = await process.communicate()
    if stdout:
        await broadcast(stdout.decode('utf-8', errors='replace').strip())
    if stderr:
        await broadcast(f"錯誤：{stderr.decode('utf-8', errors='replace').strip()}")

    if process.returncode == 0:
        await broadcast("伺服器：所有依賴安裝完成，主服務已啟動。")
        await broadcast("INSTALLATION_COMPLETE")
    else:
        await broadcast(f"伺服器：安裝過程發生錯誤，返回碼：{process.returncode}")
        await broadcast("INSTALLATION_FAILED")


@app.on_event("startup")
async def startup_event():
    """伺服器啟動時，在背景異步執行安裝任務"""
    asyncio.create_task(run_installer_and_broadcast())


# --- WebSocket 端點 ---

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """處理 WebSocket 連接，用於即時狀態更新"""
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # 歡迎訊息
        await websocket.send_text("伺服器：連接成功！正在等待依賴安裝進度...")
        # 保持連接開啟，以接收來自服務端的廣播
        while True:
            await websocket.receive_text() # 等待客戶端可能發送的訊息 (雖然目前不會處理)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        print("一個客戶端已斷開連接")


# --- 靜態檔案服務 ---

# 掛載 /assets 目錄
app.mount("/assets", StaticFiles(directory=os.path.join(vue_app_dist_path, "assets")), name="assets")

# 捕獲所有其他路由，並回傳 Vue 應用的主頁
@app.get("/{full_path:path}")
async def serve_vue_app(full_path: str):
    """
    提供 Vue 應用程式的 index.html。
    這是為了支援 SPA (單頁應用) 的路由模式，無論前端路由是什麼，都回傳主入口檔案。
    """
    return FileResponse(os.path.join(vue_app_dist_path, "index.html"))

# --- 主程式入口 (用於直接執行測試) ---
if __name__ == "__main__":
    import uvicorn
    print(f"靜態檔案目錄: {vue_app_dist_path}")
    print(f"安裝腳本: {installer_script_path}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
