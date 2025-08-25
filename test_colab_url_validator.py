# 繁體中文註解：
# 這個檔案專門用來測試 Colabpro.py 中的 Colab 網址驗證器 (_get_colab_url) 的負向路徑。
# Pytest 版本的測試，使用 monkeypatch fixture。

import unittest
from unittest.mock import MagicMock
import sys
import os
import pytest

# 為了能從測試檔案中導入 Colabpro.py 的類別，我們需要將專案根目錄加入到 sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 我們需要 mock 掉一些 Colab 特有的模組，使其在本地環境也能被導入
MOCK_MODULES = {
    'google.colab': MagicMock(),
    'google.colab.output': MagicMock(),
    'IPython': MagicMock(),
    'IPython.display': MagicMock(),
    'pytz': MagicMock()
}
# 這一次，我們在導入 Colabpro 之前就先 patch sys.modules
# 這確保 Colabpro 在被 Python 首次加載時，就看到這些 mock 好的模組
from unittest.mock import patch
with patch.dict('sys.modules', MOCK_MODULES):
    from Colabpro import TunnelManager, DisplayManager, requests, colab_output

# 使用 pytest 的 class-based tests
class TestColabUrlValidator:

    # Pytest 會自動注入 monkeypatch fixture
    def setup_method(self, method):
        """在每個測試前執行，設定一個乾淨的環境。"""
        self.shared_state = {"urls": {}}
        self.mock_log_manager = MagicMock(spec=DisplayManager)
        self.mock_log_manager.log = MagicMock()

        self.tunnel_manager = TunnelManager(
            port=8000,
            shared_state=self.shared_state,
            project_path='.',
            log_manager=self.mock_log_manager,
            timeout=5
        )

    def test_rejects_url_with_network_error(self, monkeypatch):
        """
        測試案例：當 requests.head 拋出網路錯誤時，驗證器應將其視為失敗並重試。
        """
        # 設定 Monkeypatch
        monkeypatch.setattr('Colabpro.IN_COLAB', True)
        mock_eval_js = MagicMock(return_value="http://some-valid-looking-but-fake-url.colab.dev")
        # 正確的 patch目標是 colab_output 物件上的 eval_js 方法
        monkeypatch.setattr(colab_output, 'eval_js', mock_eval_js)

        from requests.exceptions import RequestException
        # 我們讓 mock 的 head 函式拋出一個我們可識別的錯誤
        mock_requests_head = MagicMock(side_effect=RequestException("Simulated network error"))
        monkeypatch.setattr(requests, 'head', mock_requests_head)

        # 執行
        self.tunnel_manager._get_colab_url()

        # 斷言
        assert mock_eval_js.called
        assert mock_requests_head.called
        log_calls = self.mock_log_manager.log.call_args_list

        # 修正後的斷言：我們檢查外層 except 區塊捕獲到的、更通用的錯誤日誌。
        # 這能正確反映程式碼的實際行為。
        assert any("次嘗試時發生錯誤: Simulated network error" in call.args[1] for call in log_calls)
        assert "錯誤" in self.shared_state["urls"]["Colab"]["url"]

    def test_rejects_url_with_bad_status_code(self, monkeypatch):
        """
        測試案例：當 requests.head 回傳一個失敗的 HTTP 狀態碼時，驗證器應將其視為失敗。
        """
        # 設定 Monkeypatch
        monkeypatch.setattr('Colabpro.IN_COLAB', True)
        mock_eval_js = MagicMock(return_value="http://another-fake-url.colab.dev")
        monkeypatch.setattr(colab_output, 'eval_js', mock_eval_js)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests_head = MagicMock(return_value=mock_response)
        monkeypatch.setattr(requests, 'head', mock_requests_head)

        # 執行
        self.tunnel_manager._get_colab_url()

        # 斷言
        log_calls = self.mock_log_manager.log.call_args_list
        assert any("收到不成功的狀態碼: 404" in call.args[1] for call in log_calls)
        assert "錯誤" in self.shared_state["urls"]["Colab"]["url"]

    def test_accepts_url_with_good_status_code(self, monkeypatch):
        """
        測試案例：當 requests.head 回傳一個成功的 HTTP 狀態碼時，驗證器應將其視為成功。
        """
        # 設定 Monkeypatch
        monkeypatch.setattr('Colabpro.IN_COLAB', True)
        test_url = "http://perfectly-fine-url.colab.dev"
        mock_eval_js = MagicMock(return_value=test_url)
        monkeypatch.setattr(colab_output, 'eval_js', mock_eval_js)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_head = MagicMock(return_value=mock_response)
        monkeypatch.setattr(requests, 'head', mock_requests_head)

        # 執行
        self.tunnel_manager._get_colab_url()

        # 斷言
        log_calls = self.mock_log_manager.log.call_args_list
        assert any(f"網址驗證成功 (狀態碼: 200)" in call.args[1] for call in log_calls)
        assert self.shared_state["urls"]["Colab"]["url"] == test_url
