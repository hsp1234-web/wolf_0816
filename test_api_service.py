# 這是我們新的後端服務級整合測試檔案。
# 我們將在這裡使用 Pytest 和 FastAPI 的 TestClient 來為我們的 API 建立測試，
# 確保在重構過程中和重構之後，核心功能依然穩定。

import pytest
from fastapi.testclient import TestClient

# 我們正在將所有後端邏輯統一到 `src/main.py`。
# 因此，我們的測試現在也應該指向這個新的、統一的 app 實例。
from src.main import app

client = TestClient(app)

def test_serve_vue_app_root():
    """
    測試根路徑 ('/') 是否能成功回傳 Vue 應用的主頁 HTML。
    這是最基本的健康檢查，確保 FastAPI 應用能正常啟動並提供前端服務。
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<h1>500: Frontend Not Built</h1>" not in response.text

def test_get_models_config():
    """
    測試 `/api/models` 端點是否能成功讀取並回傳 `models.json` 的內容。
    """
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "transcription_models" in data
    assert "youtube_report_models" in data
    assert isinstance(data["transcription_models"], list)
