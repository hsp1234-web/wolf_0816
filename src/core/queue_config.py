# 繁體中文註解：
# 這個模組是 Huey 實例的「單一事實來源 (Single Source of Truth)」。
# 它被設計為專案中最基礎的模組之一，不應該導入任何其他的本地專案模組。
# 這可以從根本上防止因導入 `huey` 實例而引發的循環依賴問題。

from huey import SqliteHuey
from pathlib import Path

# 向上追溯兩層以找到專案根目錄 (src/core -> src -> ROOT)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# 將 Huey 的 SQLite 資料庫檔案放置在專案的根目錄下
QUEUE_DB_PATH = ROOT_DIR / "queue.db"

# 建立並匯出共享的 Huey 實例。
# 專案中任何需要使用 huey 的地方都應該從這裡導入。
huey = SqliteHuey(filename=str(QUEUE_DB_PATH))
