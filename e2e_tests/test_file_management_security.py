import pytest
from unittest.mock import patch

from services.file_management_service.main import check_disk_capacity

# 我們對 'services.file_management_service.main.shutil.disk_usage' 進行修補，
# 因為這是 `shutil` 模組在 `check_disk_capacity` 函式中被使用的地方。
@patch('services.file_management_service.main.shutil.disk_usage')
def test_disk_capacity_sufficient(mock_disk_usage):
    """測試案例：當磁碟使用率充足時，檢查應該順利通過且不拋出任何錯誤。"""
    # 安排: 模擬 50% 的磁碟使用率
    mock_disk_usage.return_value = (100 * 1024**3, 50 * 1024**3, 50 * 1024**3)

    # 行動與斷言: 呼叫函式，預期不會發生任何事。如果拋出例外，測試將會失敗。
    try:
        check_disk_capacity()
    except RuntimeError:
        pytest.fail("當磁碟空間足夠時，不應拋出 RuntimeError。")

    mock_disk_usage.assert_called_once_with('/')

@patch('services.file_management_service.main.shutil.disk_usage')
def test_disk_capacity_at_threshold(mock_disk_usage):
    """測試案例：當磁碟使用率正好在閾值時，應拋出 RuntimeError。"""
    # 安排: 模擬 80% 的磁碟使用率
    mock_disk_usage.return_value = (100 * 1024**3, 80 * 1024**3, 20 * 1024**3)

    # 行動與斷言
    with pytest.raises(RuntimeError) as excinfo:
        check_disk_capacity()

    assert "錯誤碼 102" in str(excinfo.value)
    mock_disk_usage.assert_called_once_with('/')

@patch('services.file_management_service.main.shutil.disk_usage')
def test_disk_capacity_over_threshold(mock_disk_usage):
    """測試案例：當磁碟使用率超過閾值時，應拋出 RuntimeError。"""
    # 安排: 模擬 95% 的磁碟使用率
    mock_disk_usage.return_value = (100 * 1024**3, 95 * 1024**3, 5 * 1024**3)

    with pytest.raises(RuntimeError) as excinfo:
        check_disk_capacity()

    assert "錯誤碼 102" in str(excinfo.value)
    mock_disk_usage.assert_called_once_with('/')

@patch('services.file_management_service.main.shutil.disk_usage')
def test_disk_capacity_file_not_found_handled(mock_disk_usage, caplog):
    """測試案例：當發生 FileNotFoundError 時，應記錄警告且不拋出錯誤。"""
    # 安排: 模擬拋出 FileNotFoundError
    mock_disk_usage.side_effect = FileNotFoundError("目錄不存在")

    # 行動: 呼叫函式
    check_disk_capacity()

    # 斷言: 確認日誌中記錄了警告訊息
    assert "無法找到根目錄" in caplog.text
    mock_disk_usage.assert_called_once_with('/')

@patch('services.file_management_service.main.shutil.disk_usage')
def test_disk_capacity_other_exception_handled(mock_disk_usage):
    """測試案例：當發生其他未知錯誤時，應拋出包含錯誤碼 103 的 RuntimeError。"""
    # 安排: 模擬拋出通用例外
    mock_disk_usage.side_effect = Exception("未知錯誤")

    with pytest.raises(RuntimeError) as excinfo:
        check_disk_capacity()

    assert "錯誤碼 103" in str(excinfo.value)
    mock_disk_usage.assert_called_once_with('/')
