import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client():
    """
    提供一個 FastAPI TestClient 實例。

    這個 fixture 的關鍵在於：它在 `main` 模組被匯入之前，
    就先對 `check_disk_capacity` 函式進行了模擬 (patch)。
    這可以防止在測試期間執行真實的磁碟檢查，確保了 API 測試的隔離性。
    """
    # 在匯入 app 之前，先模擬掉啟動時會執行的函式
    with patch('services.file_management_service.main.check_disk_capacity') as mock_check:
        # 現在可以安全地匯入 app，此時 app 啟動事件中的 check_disk_capacity 已被模擬
        from services.file_management_service.main import app

        # 使用 TestClient，並在其上下文管理器中執行測試
        with TestClient(app) as test_client:
            yield test_client # 將 test_client 提供給測試函式

def test_health_check(client):
    """
    測試服務的健康檢查端點 (`/`) 是否正常運作。
    """
    # 行動: 對根端點發出 GET 請求
    response = client.get("/")

    # 斷言: 確認狀態碼為 200 (OK)
    assert response.status_code == 200
    # 斷言: 確認回傳的 JSON 內容符合預期
    assert response.json() == {"status": "ok", "service": "File Management Service"}
