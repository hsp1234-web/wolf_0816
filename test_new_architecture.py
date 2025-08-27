# test_new_architecture.py
import time
import requests
import subprocess
import sys
import pytest
import logging
from pathlib import Path
import json
import uuid

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- 測試設定 ---
PROJECT_ROOT = Path(__file__).parent.resolve()
API_PORT = 8000  # 與 Colabpro.py 中設定的 API 伺服器埠號一致
API_URL = f"http://127.0.0.1:{API_PORT}"
HEALTH_CHECK_URL = f"{API_URL}/api/health"
GET_TASKS_URL = f"{API_URL}/api/tasks"
POST_TASK_URL = f"{API_URL}/api/tasks"

@pytest.fixture(scope="module")
def services():
    """
    一個 Pytest Fixture，負責在測試開始前啟動所有必要的背景服務，
    並在測試結束後將它們全部關閉。
    """
    processes = []
    log.info("--- 測試設定：正在啟動所有背景服務 ---")

    try:
        # 1. 啟動資料庫管理器
        log.info("啟動資料庫管理器 (db_manager.py)...")
        db_proc = subprocess.Popen(
            [sys.executable, "src/db/manager.py"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8'
        )
        processes.append(("DB Manager", db_proc))
        time.sleep(3) # 給予啟動時間

        # 2. 啟動 API 伺服器
        log.info(f"啟動統一 API 伺服器 (api_server.py) 於埠號 {API_PORT}...")
        api_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.api_server:app", "--port", str(API_PORT)],
            cwd=PROJECT_ROOT,
            text=True,
            encoding='utf-8'
        )
        processes.append(("API Server", api_proc))
        time.sleep(3)

        # 3. 啟動轉錄工作者
        log.info("啟動轉錄工作者 (transcription_worker.py)...")
        worker_proc = subprocess.Popen(
            [sys.executable, "workers/transcription_worker.py"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8'
        )
        processes.append(("Transcription Worker", worker_proc))
        time.sleep(2)

        # 4. 等待 API 伺服器就緒
        log.info("等待 API 伺服器健康檢查通過...")
        start_time = time.time()
        while time.time() - start_time < 30: # 30 秒超時
            try:
                response = requests.get(HEALTH_CHECK_URL, timeout=1)
                if response.status_code == 200:
                    log.info("✅ API 伺服器已就緒。")
                    break
            except requests.ConnectionError:
                time.sleep(1)
        else:
            raise RuntimeError("API 伺服器在 30 秒內未能啟動。")

        # 使用 yield 將控制權交還給測試函式
        yield

    finally:
        # --- 測試清理 ---
        log.info("--- 測試清理：正在關閉所有背景服務 ---")
        for name, proc in reversed(processes):
            if proc.poll() is None:
                log.info(f"正在終止 {name} (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log.warning(f"{name} (PID: {proc.pid}) 未能在 5 秒內終止，強制終止。")
                    proc.kill()
        log.info("--- 所有服務已關閉 ---")


def test_full_transcription_flow(services):
    """
    一個完整的端對端測試，驗證從任務建立到完成的整個流程。
    """
    # 1. 建立一個新的轉錄任務
    log.info("步驟 1: 建立一個新的轉錄任務...")
    task_payload = {
        "type": "transcribe",
        "payload": {
            "original_filename": "test_audio.wav"
        }
    }
    response = requests.post(POST_TASK_URL, json=task_payload)
    assert response.status_code == 201
    task_data = response.json()
    task_id = task_data.get("task_id")
    assert task_id is not None
    log.info(f"✅ 任務建立成功，Task ID: {task_id}")

    # 2. 輪詢任務狀態，直到其完成或失敗
    log.info(f"步驟 2: 輪詢任務 {task_id} 的狀態...")
    start_time = time.time()
    final_status = None
    while time.time() - start_time < 30: # 30 秒的測試超時
        all_tasks_response = requests.get(GET_TASKS_URL)
        assert all_tasks_response.status_code == 200
        all_tasks = all_tasks_response.json()

        current_task = next((t for t in all_tasks if t['task_id'] == task_id), None)
        assert current_task is not None, f"任務 {task_id} 從 API 回應中消失了！"

        current_status = current_task['status']
        log.info(f"  -> 當前狀態: {current_status}, 進度: {current_task['progress']}%")

        if current_status in ["completed", "failed"]:
            final_status = current_status
            break

        time.sleep(1)

    # 3. 驗證最終狀態和結果
    log.info("步驟 3: 驗證最終結果...")
    assert final_status == "completed", f"任務最終狀態應為 'completed'，但卻是 '{final_status}'"

    final_task_data = next((t for t in requests.get(GET_TASKS_URL).json() if t['task_id'] == task_id), {})
    assert "result" in final_task_data
    result_data = json.loads(final_task_data["result"])
    assert "transcription" in result_data
    assert "test_audio.wav" in result_data["transcription"]
    log.info(f"✅ 測試成功！任務 {task_id} 已正確完成，並包含預期的結果。")
