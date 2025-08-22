import datetime
import pytz

def get_taipei_iso_time():
    """
    獲取當前亞洲/台北時區的時間，並以 ISO 8601 格式回傳。
    格式: YYYY-MM-DDTHH:MM:SS+08:00
    """
    # 定義台北時區
    taipei_tz = pytz.timezone('Asia/Taipei')

    # 獲取當前的台北時間
    now_taipei = datetime.datetime.now(taipei_tz)

    # 格式化為 ISO 8601 字串，並確保時區資訊正確
    # isoformat() 會產生像 +08:00 這樣的時區偏移
    return now_taipei.isoformat()

if __name__ == "__main__":
    # 當此腳本被直接執行時，印出當前的時間戳記
    print(get_taipei_iso_time())
