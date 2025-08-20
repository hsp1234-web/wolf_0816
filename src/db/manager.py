# db/manager.py
#
# --- 執行與管理說明 (由 Jules 於 2025-08-12 新增) ---
#
# **重要：** 此腳本不應該被直接執行。
#
# 本檔案定義了一個作為背景服務運行的 TCP 伺服器，負責管理所有資料庫操作。
# 為了避免因程序未被正確關閉而導致的資源衝突（即「殭屍程序」問題），
# 此服務的生命週期由 `circus` 程序管理器進行統一管理。
#
# **標準啟動方式：**
# 1. **透過 `run_tests.py`**：這是執行測試的標準方法。
#    `run_tests.py` 會自動處理以下所有步驟：
#      a. 清理舊的程序和檔案。
#      b. 使用 `circus` 啟動此 `db_manager` 和 `api_server`。
#      c. 執行 `pytest` 測試。
#      d. 在測試結束後，確保所有服務都被優雅關閉。
#
# 2. **手動啟動 (開發時)**：若需手動啟動，應使用 `circus`：
#    `python -m circus.circusd circus.ini`
#
# 透過 `run_tests.py` 或 `circus` 來管理，可以從根本上解決
# 因資源（埠號、資料庫檔案）被占用而導致的啟動失敗問題。
#
# --- 程式碼開始 ---
import socketserver
import json
import logging
import sqlite3
import sys
from pathlib import Path

# 讓此腳本可以存取上層目錄的 db.database 模組
sys.path.append(str(Path(__file__).resolve().parent.parent))
from db import database

# --- 日誌設定 ---
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger('DBManagerServer')

# --- 伺服器設定 ---
HOST = "127.0.0.1"
PORT_FILE = Path(__file__).parent / "db_manager.port"
READY_FILE = Path(__file__).parent / "db_manager.ready" # JULES'S FIX: 新增一個「就緒」信號檔案

# --- 指令分派 ---
ACTION_MAP = {
    "initialize_database": database.initialize_database,
    "add_task": database.add_task,
    "fetch_and_lock_task": database.fetch_and_lock_task,
    "update_task_progress": database.update_task_progress,
    "update_task_status": database.update_task_status,
    "get_task_status": database.get_task_status,
    "are_tasks_active": database.are_tasks_active,
    "get_all_tasks": database.get_all_tasks,
    "get_system_logs": database.get_system_logs_by_filter,
    "add_system_log": database.add_system_log,
    "find_dependent_task": database.find_dependent_task,
    "get_app_state": database.get_app_state,
    "set_app_state": database.set_app_state,
    "check_tables_exist": database.check_tables_exist,
    "delete_task": database.delete_task,
}

class DBRequestHandler(socketserver.BaseRequestHandler):
    """
    處理來自客戶端請求的處理器。
    """
    def handle(self):
        log.info(f"來自 {self.client_address} 的新連線。")
        try:
            while True:
                header = self.request.recv(4)
                if not header: break
                data_len = int.from_bytes(header, 'big')
                data = self.request.recv(data_len)
                if not data: break

                request = json.loads(data.decode('utf-8'))
                log.info(f"收到請求: {request}")

                action = request.get("action")
                params = request.get("params", {})
                response = {}
                try:
                    if action in ACTION_MAP:
                        func = ACTION_MAP[action]
                        result = func(**params)
                        response["status"] = "success"
                        response["data"] = result
                    else:
                        response["status"] = "error"
                        response["message"] = f"未知的 action: {action}"
                        log.warning(f"收到了未知的 action: {action}")
                except Exception as e:
                    log.error(f"執行 action '{action}' 時發生錯誤: {e}", exc_info=True)
                    response["status"] = "error"
                    response["message"] = f"執行 '{action}' 時發生內部錯誤: {str(e)}"

                response_bytes = json.dumps(response).encode('utf-8')
                response_header = len(response_bytes).to_bytes(4, 'big')
                self.request.sendall(response_header + response_bytes)
        except ConnectionResetError:
            log.warning(f"客戶端 {self.client_address} 強制中斷了連線。")
        except Exception as e:
            log.error(f"處理連線 {self.client_address} 時發生未預期的錯誤: {e}", exc_info=True)
        finally:
            log.info(f"連線 {self.client_address} 已關閉。")

def run_server():
    """
    啟動資料庫管理者伺服器。
    """
    try:
        log.info("資料庫管理者伺服器啟動前，正在進行資料庫初始化...")
        # JULES'S FIX: 清理上一次可能遺留的 ready 檔案
        if READY_FILE.exists():
            READY_FILE.unlink()
        database.initialize_database()
        log.info("✅ 資料庫初始化成功。")
        # JULES'S FIX: 建立「就緒」檔案作為明確信號
        READY_FILE.touch()
        log.info(f"✅ 已建立就緒信號檔案: {READY_FILE}")
    except (sqlite3.Error, IOError) as e:
        log.critical(f"❌ 資料庫初始化或建立就緒檔案時失敗，伺服器無法啟動: {e}")
        sys.exit(1)

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer((HOST, 0), DBRequestHandler) as server:
            actual_port = server.server_address[1]
            log.info(f"🚀 資料庫管理者伺服器已在 {HOST}:{actual_port} 上啟動...")
            try:
                PORT_FILE.write_text(str(actual_port))
                log.info(f"已將埠號寫入: {PORT_FILE}")
            except IOError as e:
                log.critical(f"❌ 無法寫入埠號檔案，客戶端將無法連線: {e}")
                sys.exit(1)

            try:
                server.serve_forever()
            finally:
                log.info("伺服器正在關閉...")
                for f in [PORT_FILE, READY_FILE]:
                    try:
                        if f.exists():
                            f.unlink()
                    except IOError as e:
                        log.warning(f"清理信號檔案 {f} 時發生錯誤: {e}")
    except Exception as e:
        log.critical(f"🔥 啟動 DB Manager 伺服器時發生嚴重錯誤: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run_server()
