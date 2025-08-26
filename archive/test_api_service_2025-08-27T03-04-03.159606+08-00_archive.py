# -*- coding: utf-8 -*-
# 這是我們新的後端服務級整合測試檔案。
# 我們將在這裡使用 Pytest 和 FastAPI 的 TestClient 來為我們的 API 建立測試，
# 確保在重構過程中和重構之後，核心功能依然穩定。

import pytest
from fastapi.testclient import TestClient

# 這個導入現在是安全的，因為 conftest.py 中的 `baked_env` fixture
# 會在 pytest 收集此檔案之前運行，並設定好所有必要的依賴路徑。
from src.core.mini_server import app

@pytest.fixture(scope="module")
def api_client():
    """
    一個模組級的 fixture，提供一個 FastAPI TestClient 實例。

    使用 fixture 可以確保 `TestClient(app)` 的實例化
    發生在 `baked_env` fixture 成功準備好環境之後。
    """
    with TestClient(app) as client:
        yield client

def test_serve_vue_app_root(api_client):
    """
    測試根路徑 ('/') 是否能成功回傳 Vue 應用的主頁 HTML。
    這是最基本的健康檢查，確保 FastAPI 應用能正常啟動並提供前端服務。
    """
    response = api_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # 這裡的檢查點是，我們不應該看到一個錯誤頁面
    assert "<h1>500: Frontend Not Built</h1>" not in response.text
    # 也不應該是空的 body
    assert len(response.content) > 100

def test_get_models_config(api_client):
    """
    測試 `/api/models` 端點是否能成功讀取並回傳 `models.json` 的內容。
    """
    response = api_client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "transcription_models" in data
    assert "youtube_report_models" in data
    assert isinstance(data["transcription_models"], list)
