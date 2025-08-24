import sys
from pathlib import Path
import os
from unittest.mock import MagicMock

# --- 模擬 Colab 環境依賴 ---
# 為了在非 Colab 環境中測試 Colab.py，我們需要模擬它所依賴的模組
mock_ipython = MagicMock()
mock_ipython.display.clear_output = MagicMock()
mock_ipython.display.display = MagicMock()
mock_ipython.display.HTML = MagicMock()
sys.modules['IPython'] = mock_ipython
sys.modules['IPython.display'] = mock_ipython.display

mock_google_colab = MagicMock()
# 我們不需要這些函式有實際行為，只需要它們存在即可
mock_google_colab.output.eval_js.return_value = {"url": "http://fake-proxy-url-for-test.localhost"}
mock_google_colab.userdata.get.return_value = None
# 建立一個假的 google 模組，因為 `from google.colab` 需要它
mock_google = MagicMock()
mock_google.colab = mock_google_colab
sys.modules['google'] = mock_google
sys.modules['google.colab'] = mock_google_colab
# --- 模擬結束 ---

# 確保能從根目錄導入 Colab.py
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import Colab
except ImportError as e:
    print(f"無法導入 Colab.py: {e}", file=sys.stderr)
    print("請確保此腳本是從專案根目錄的子目錄 'runner' 中執行的。", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    print("--- Wrapper: 正在啟動 Colab.py 的 main() 函式 ---")
    Colab.main(project_path_str=str(ROOT_DIR))
    print("--- Wrapper: Colab.py 的 main() 函式已結束 ---")
