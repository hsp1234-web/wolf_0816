import time
import traceback
from src.core.queue_config import huey
from .logging_worker import add_log

# 導入新的狀態管理器和 AppState 模型
from src.core.state_manager import state_manager, AppState

@huey.task()
def process_transcription(task_id: str, file_path: str, original_filename: str):
    """
    這是一個轉錄任務的真正實作。
    它會透過 state_manager 更新 AppState 中的任務狀態。
    """
    worker_name = "transcription_worker"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始處理任務: {original_filename} ---")

    # 輔助函式，用於在 AppState 中尋找並更新任務
    def update_task_in_state(state: AppState, status: str, result: dict = None, error: str = None):
        task_index = -1
        for i, t in enumerate(state.pending_tasks):
            if t.task_id == task_id:
                task_index = i
                break

        if task_index == -1:
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] 在 pending_tasks 中找不到任務！")
            return

        task = state.pending_tasks[task_index]
        task.status = status

        if error:
            task.result = {"error": error}
            # 任務失敗，移至 completed_tasks
            state.completed_tasks.append(state.pending_tasks.pop(task_index))
        elif status == "completed":
            task.result = result
            # 任務成功，移至 completed_tasks
            state.completed_tasks.append(state.pending_tasks.pop(task_index))
        # 其他狀態（如 processing）則保留在 pending_tasks 中

    try:
        # 1. 將任務狀態更新為 "processing"
        add_log(worker_name, "DEBUG", f"[Task ID: {task_id}] 更新狀態為 'processing'")
        state_manager.update_state(
            lambda state: update_task_in_state(state, status="processing")
        )

        # 2. 模擬耗時的 AI 處理
        add_log(worker_name, "INFO", f"[Task ID: {task_id}] 正在進行模擬轉錄...")
        time.sleep(10) # 模擬 10 秒的處理時間
        result_text = f"這是 '{original_filename}' 的模擬轉錄結果。"

        # 3. 處理成功，將任務狀態更新為 "completed"
        add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] 轉錄完成")
        state_manager.update_state(
            lambda state: update_task_in_state(state, status="completed", result={"transcription": result_text})
        )

    except Exception as e:
        error_message = f"處理失敗: {str(e)}"
        add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")

        # 4. 處理失敗，將任務狀態更新為 "failed"
        state_manager.update_state(
            lambda state: update_task_in_state(state, status="failed", error=error_message)
        )
    finally:
        add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 任務處理流程結束 ---")

# 這部分不是必須的，因為我們將透過 huey_consumer.py 來啟動 worker。
# 但保留它可以方便單獨測試這個 worker。
if __name__ == '__main__':
    print("警告：此腳本不應直接執行。")
    print("請執行 `huey_consumer.py` 來啟動工作者。")
