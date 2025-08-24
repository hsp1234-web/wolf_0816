# 繁體中文註解：
# 這個腳本是 Huey 消費者進程的官方入口點。
# Huey 的命令列工具 (`huey_consumer.py`) 會執行此檔案來啟動背景工作處理器。

# 1. 從新的中央設定檔導入共享的 `huey` 實例。
#    這使得 Huey 的執行器可以找到它需要操作的佇列物件。
from src.core.queue_config import huey

# 2. 導入任務註冊模組。
#    這一行至關重要。它會執行 `src/huey_tasks.py`，進而導入所有的 worker 模組，
#    確保所有 `@huey.task()` 裝飾的函式都被 Huey 實例知曉。
#    如果沒有這一行，消費者將會啟動，但不會處理任何任務。
import src.huey_tasks
