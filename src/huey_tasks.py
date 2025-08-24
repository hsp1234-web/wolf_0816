# 繁體中文註解：
# 這個模組的唯一目的是「註冊任務」。
# 它透過導入共享的 `huey` 實例，然後再導入所有包含任務定義的 worker 模組，
# 來確保 Huey 能夠發現所有 `@huey.task()` 裝飾的函式。
# 主應用程式或消費者啟動器只需要 `import src.huey_tasks` 即可完成所有任務的註冊。

from src.core.queue_config import huey

# --- 任務註冊 ---
# 導入下面的模組以註冊其中定義的 Huey 任務。
import workers.transcription_worker
import workers.logging_worker
