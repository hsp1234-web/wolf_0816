import threading
from typing import List, Dict, Any, Callable
from pydantic import BaseModel, Field
import jsonpatch
from copy import deepcopy

# --- 狀態的 Pydantic 模型定義 ---
# 這些模型定義了 AppState 的結構，確保了型別安全。

class WorkerStatus(BaseModel):
    status: str = "PENDING"
    last_error: str | None = None

class OperationStatus(BaseModel):
    in_progress: bool = False
    message: str = ""
    progress: int = 0

class LocalModelsStatus(BaseModel):
    available: List[str] = []
    checking: bool = True

class Task(BaseModel):
    task_id: str
    type: str
    status: str = "pending"
    payload: Dict[str, Any] = {}
    result: Dict[str, Any] | None = None
    created_at: str

class AppState(BaseModel):
    """
    單一應用程式狀態 (Single Application State)
    這是整個應用程式後端的「單一事實來源」。
    """
    pending_tasks: List[Task] = []
    completed_tasks: List[Task] = []
    worker_statuses: Dict[str, WorkerStatus] = {}
    operation_status: OperationStatus = Field(default_factory=OperationStatus)
    local_models: LocalModelsStatus = Field(default_factory=LocalModelsStatus)
    # 可以在此處新增更多狀態欄位

# --- 中央狀態管理器 ---

class StateManager:
    """
    管理 AppState 的生命週期，並處理狀態的變更與補丁生成。
    """
    def __init__(self):
        self._state = AppState()
        self._lock = threading.Lock()
        self._patch_listeners: List[Callable[[List[Dict]], None]] = []

    def get_full_state(self) -> Dict:
        """獲取當前狀態的完整深拷貝字典。"""
        with self._lock:
            return self._state.model_dump(mode='json')

    def update_state(self, updater: Callable[[AppState], None]):
        """
        以安全的方式更新狀態，並生成和廣播補丁。

        :param updater: 一個接收 AppState 物件並直接對其進行修改的函式。
        """
        with self._lock:
            old_state_dict = self._state.model_dump(mode='json')

            # 建立一個狀態的深拷貝以進行修改
            state_copy = deepcopy(self._state)
            updater(state_copy)

            # 更新主狀態
            self._state = state_copy
            new_state_dict = self._state.model_dump(mode='json')

        # 在鎖之外生成和廣播補丁
        patch = jsonpatch.make_patch(old_state_dict, new_state_dict)
        patch_list = patch.patch

        if patch_list:
            print(f"狀態已更新，生成補丁: {patch_list}")
            for listener in self._patch_listeners:
                listener(patch_list)

    def add_patch_listener(self, listener: Callable[[List[Dict]], None]):
        """
        註冊一個監聽器，當狀態產生補丁時會被呼叫。
        主要由 notification_service 使用。
        """
        self._patch_listeners.append(listener)

# --- 全域實例 ---
# 應用程式的其他部分將導入此實例來與中央狀態互動。
state_manager = StateManager()

# --- 範例使用 (僅供測試) ---
if __name__ == '__main__':
    def print_patch(p):
        print(f"監聽器收到補丁: {p}")

    state_manager.add_patch_listener(print_patch)

    print("--- 初始狀態 ---")
    print(state_manager.get_full_state())

    print("\n--- 新增一個工作者狀態 ---")
    def add_worker(state: AppState):
        state.worker_statuses["transcription_worker"] = WorkerStatus(status="INSTALLING")

    state_manager.update_state(add_worker)

    print("\n--- 當前狀態 ---")
    print(state_manager.get_full_state())

    print("\n--- 更新一個工作者狀態 ---")
    def update_worker(state: AppState):
        state.worker_statuses["transcription_worker"].status = "IDLE"

    state_manager.update_state(update_worker)

    print("\n--- 當前狀態 ---")
    print(state_manager.get_full_state())
