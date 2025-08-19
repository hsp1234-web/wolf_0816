# runner/tests/test_localrun_protections.py
import pytest
from unittest.mock import patch
import sys
from pathlib import Path

# 為了讓 Python 能夠找到 'runner.localrun' 模組，我們需要將專案的根目錄加入到系統路徑中
# 測試檔案位於 runner/tests/，所以根目錄是上三層
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 現在我們可以安全地從腳本中匯入所需的類別
from runner.localrun import StagedLauncher

@pytest.fixture
def launcher():
    """提供一個乾淨的 StagedLauncher 實例供每個測試使用。"""
    return StagedLauncher(mock_mode=True)

# 我們對 'runner.localrun.shutil.disk_usage' 進行修補 (patch)，
# 因為這是 `shutil` 模組被匯入並在 `_check_disk_capacity` 中被使用的地方。
@patch('runner.localrun.shutil.disk_usage')
def test_disk_capacity_sufficient(mock_disk_usage, launcher):
    """測試案例：當磁碟使用率充足（< 80%）時，檢查應該通過。"""
    # 安排 (Arrange): 模擬 50% 的磁碟使用率。回傳值的單位是 bytes。
    mock_disk_usage.return_value = (100 * 1024**3, 50 * 1024**3, 50 * 1024**3)

    # 行動 (Act): 執行磁碟容量檢查
    result = launcher._check_disk_capacity()

    # 斷言 (Assert): 確認函式返回 True，並且 mock 物件被正確地呼叫了一次。
    assert result is True
    mock_disk_usage.assert_called_once_with('/')

@patch('runner.localrun.shutil.disk_usage')
def test_disk_capacity_at_threshold(mock_disk_usage, launcher):
    """測試案例：當磁碟使用率正好在閾值（80%）時，應該拋出錯誤。"""
    # 安排: 模擬 80% 的磁碟使用率
    mock_disk_usage.return_value = (100 * 1024**3, 80 * 1024**3, 20 * 1024**3)

    # 行動與斷言: 使用 pytest.raises 作為上下文管理器來斷言會拋出 RuntimeError
    with pytest.raises(RuntimeError) as excinfo:
        launcher._check_disk_capacity()

    # 斷言拋出的錯誤訊息中包含了關鍵的「錯誤碼 102」
    assert "錯誤碼 102" in str(excinfo.value)
    mock_disk_usage.assert_called_once_with('/')

@patch('runner.localrun.shutil.disk_usage')
def test_disk_capacity_over_threshold(mock_disk_usage, launcher):
    """測試案例：當磁碟使用率超過閾值（> 80%）時，應該拋出錯誤。"""
    # 安排: 模擬 95% 的磁碟使用率
    mock_disk_usage.return_value = (100 * 1024**3, 95 * 1024**3, 5 * 1024**3)

    # 行動與斷言
    with pytest.raises(RuntimeError) as excinfo:
        launcher._check_disk_capacity()

    assert "錯誤碼 102" in str(excinfo.value)
    mock_disk_usage.assert_called_once_with('/')

@patch('runner.localrun.shutil.disk_usage')
def test_disk_capacity_file_not_found_handled(mock_disk_usage, launcher, caplog):
    """測試案例：當 shutil.disk_usage 拋出 FileNotFoundError 時，函式應該優雅地處理。"""
    # 安排: 讓 mock 物件在被呼叫時拋出 FileNotFoundError
    mock_disk_usage.side_effect = FileNotFoundError("No such file or directory: '/'")

    # 行動
    result = launcher._check_disk_capacity()

    # 斷言: 確認函式返回 True (代表成功處理了這個預期中的錯誤)
    assert result is True
    # 使用 pytest 的 caplog fixture 來捕獲日誌輸出，並斷言其中包含了警告訊息
    assert "無法找到根目錄" in caplog.text
    mock_disk_usage.assert_called_once_with('/')

@patch('runner.localrun.shutil.disk_usage')
def test_disk_capacity_other_exception_handled(mock_disk_usage, launcher):
    """測試案例：當 shutil.disk_usage 拋出其他未知錯誤時，應該拋出包含特定錯誤碼的 RuntimeError。"""
    # 安排: 讓 mock 物件拋出一個通用的 Exception
    mock_disk_usage.side_effect = Exception("A generic error occurred")

    # 行動與斷言
    with pytest.raises(RuntimeError) as excinfo:
        launcher._check_disk_capacity()

    # 斷言錯誤訊息中包含了關鍵的「錯誤碼 103」
    assert "錯誤碼 103" in str(excinfo.value)
    mock_disk_usage.assert_called_once_with('/')
