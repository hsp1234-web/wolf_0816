# e2e_tests/test_feature_status.py
import time
import requests
import pytest
from urllib.parse import urljoin

# NOTE: This helper function is duplicated from test_basic_flow.py.
# Consider refactoring it into a shared conftest.py or utility module.
FEATURE_KEYS = ["whisper", "ytdlp", "gemini"]

def wait_for_features_ready(base_url: str, timeout: int = 180):
    """
    輪詢後端的 /api/features/status 端點，直到所有 AI 功能都準備就緒。
    """
    print(f"⏳ 開始輪詢功能狀態，目標 URL: {base_url}，超時: {timeout} 秒")
    start_time = time.time()
    status_url = urljoin(base_url, "/api/features/status")

    while time.time() - start_time < timeout:
        try:
            response = requests.get(status_url, timeout=5)
            response.raise_for_status()
            status_data = response.json()
            print(f"🔁 取得狀態: {status_data}")

            all_ready = all(
                status_data.get(feature) == "ready" for feature in FEATURE_KEYS
            )

            if all_ready:
                print("✅ 所有 AI 功能已準備就緒！")
                return status_data
        except requests.RequestException as e:
            print(f"⚠️ 輪詢時發生網路錯誤: {e}")
        except Exception as e:
            print(f"⚠️ 輪詢時發生未知錯誤: {e}")

        time.sleep(2)

    raise TimeoutError(f"❌ 在 {timeout} 秒內，AI 功能未全部準備就緒。")


def test_feature_status_endpoint(live_server: str):
    """
    專門測試 /api/features/status 端點的行為。
    1. 伺服器啟動時，立即檢查狀態，預期為 'installing' 或 'unavailable'。
    2. 等待功能就緒。
    3. 再次檢查狀態，預期為 'ready'。
    """
    base_url = live_server
    status_url = urljoin(base_url, "/api/features/status")

    # 步驟 1: 立即檢查初始狀態
    print("🔍 正在檢查功能的初始狀態...")
    try:
        initial_response = requests.get(status_url, timeout=5)
        initial_response.raise_for_status()
        initial_status = initial_response.json()
        print(f"✅ 成功取得初始狀態: {initial_status}")

        # 斷言初始狀態不是 'ready'
        for feature in FEATURE_KEYS:
            assert feature in initial_status, f"'{feature}' 鍵應存在於初始狀態回應中"
            initial_feature_status = initial_status.get(feature)
            assert initial_feature_status != "ready", \
                f"功能 '{feature}' 的初始狀態不應為 'ready'，但卻是 '{initial_feature_status}'"
        print("✅ 初始狀態驗證成功，功能均不處於 'ready' 狀態。")

    except requests.RequestException as e:
        pytest.fail(f"❌ 無法在測試開始時連接到狀態 API: {e}")

    # 步驟 2: 等待所有功能變為 'ready'
    final_status = wait_for_features_ready(base_url)

    # 步驟 3: 驗證最終狀態
    print("🔍 正在驗證功能的最終就緒狀態...")
    assert final_status is not None, "等待功能就緒時未收到最終狀態"
    for feature in FEATURE_KEYS:
        final_feature_status = final_status.get(feature)
        assert final_feature_status == "ready", \
            f"功能 '{feature}' 的最終狀態應為 'ready'，但卻是 '{final_feature_status}'"
    print("✅ 最終狀態驗證成功，所有功能均處於 'ready' 狀態。")

    print("🎉 功能狀態端點測試成功！")
