# services/huey_config.py
# Huey 任務佇列的中央設定檔

from huey import SqliteHuey

# 建立一個 Huey 實例，使用 SQLite 作為後端儲存。
# 'name' 參數是佇列的名稱，將用於在消費者端識別它。
# 'filename' 是 SQLite 資料庫檔案的路徑。
# 這將會在 services/ 目錄下建立一個名為 huey_queue.db 的檔案。
huey = SqliteHuey(name='app_queue', filename='services/huey_queue.db')
