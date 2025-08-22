from huey import SqliteHuey
from pathlib import Path

# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# 佇列資料庫的獨立檔案路徑
QUEUE_DB_PATH = ROOT_DIR / "queue.db"

# 建立一個使用 SQLite 作為後端的 Huey 實例。
# 這是所有任務生產者 (producer) 和消費者 (consumer) 共享的單一實例。
huey = SqliteHuey(filename=str(QUEUE_DB_PATH))
