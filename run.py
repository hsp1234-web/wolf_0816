# -*- coding: utf-8 -*-
"""
Colab 啟動器 v2.0

此腳本為 Colab 環境的唯一入口點，整合了依賴準備、後端啟動、
多通道穿透以及動態狀態顯示的完整啟動流程。

主要職責:
1.  解壓縮預先烘烤的依賴 (`dependencies.tar.gz`) 並注入執行路徑。
2.  在背景以子程序方式啟動 FastAPI/Starlette 後端伺服器。
3.  並行啟動 Cloudflare、Localtunnel 和 Colab 官方代理三種穿透通道。
4.  實現一個「漸進式刷新」的純文字 UI，即時回報後端和通道的狀態。
5.  提供優雅的關閉機制，確保所有子程序都能被正確終止。
"""
import os
import sys
import tarfile
import tempfile
import shutil
import subprocess
import time
import threading
import queue
import re
from pathlib import Path

# --- 模擬 Colab 環境，方便本地測試 ---
# 參考自 archive/Colabpro.py.legacy 的優秀設計
try:
    from google.colab import output as colab_output
    from IPython.display import clear_output
    IN_COLAB = True
except ImportError:
    class MockColabOutput:
        def eval_js(self, *args, **kwargs): return ""
    class MockDisplay:
        def clear_output(self, wait=False): print("\n--- 清除輸出 ---\n")

    colab_output = MockColabOutput()
    clear_output = MockDisplay().clear_output
    IN_COLAB = False
    print("警告：未在 Colab 環境中執行，將使用模擬的 display 功能。")

# --- 全域設定 ---
UI_REFRESH_SECONDS = 0.5
TUNNEL_ORDER = ["Cloudflare", "Localtunnel", "Colab"] # 定義通道的顯示順序

# --- UI 渲染函式 ---
def _build_and_print_ui(shared_state):
    """
    根據共享狀態字典，清除 Colab 輸出並重新繪製整個純文字 UI。
    """
    clear_output(wait=True)

    output = ["🚀 Colab 啟動器 v2.0 🚀", ""]

    # 顯示後端伺服器狀態
    server_status = shared_state.get("server_status", "正在初始化...")
    output.append(f"📦 後端服務: {server_status}")

    # 顯示通道狀態
    output.append("\n🔗 公開存取網址:")

    urls = shared_state.get("urls", {})
    all_urls_resolved = len(urls) >= len(TUNNEL_ORDER)

    for name in TUNNEL_ORDER:
        url = urls.get(name)
        if url:
            # 如果 URL 包含 "錯誤"，則用紅色標記
            if "錯誤" in str(url):
                # 簡單的 ANSI 顏色標記
                if IN_COLAB:
                    output.append(f"  - {name+':':<15} \033[91m{url}\033[0m")
                else:
                    output.append(f"  - {name+':':<15} {url} (錯誤)")
            else:
                 output.append(f"  - {name+':':<15} {url}")
        elif all_urls_resolved:
            # 如果所有通道都已處理完，但這個通道沒有 URL，說明它失敗了
            output.append(f"  - {name+':':<15} (啟動失敗)")
        else:
            # 否則，它仍在處理中
            output.append(f"  - {name+':':<15} (正在產生...)")

    # 最終狀態訊息
    if shared_state.get("all_done"):
         output.append("\n✅ 應用程式已就緒！")

    # 打印所有內容
    print("\n".join(output))

# --- 通道管理器 ---
# 這是任務 2.1 和 2.2 的基礎結構
class TunnelManager:
    """負責並行啟動和管理多個穿透通道。"""
    def __init__(self, port, shared_state, timeout=20):
        self.port = port
        self._state = shared_state
        self._timeout = timeout
        self.threads = []
        self.processes = [] # 用於追蹤由通道建立的子程序

    def _run_tunnel_service(self, name, command, pattern):
        """
        一個通用的函式，用於啟動一個子程序並從其輸出中解析 URL。
        參考自 archive/Colabpro.py.legacy 的實作。
        """
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            self.processes.append(proc)

            start_time = time.monotonic()
            while time.monotonic() - start_time < self._timeout:
                line = proc.stdout.readline()
                if not line:
                    break
                match = re.search(pattern, line)
                if match:
                    url = match.group(1)
                    self._state["urls"][name] = url
                    # 成功找到 URL，讓程序在背景繼續運行
                    return
                time.sleep(0.1)
            # 如果超時後仍未找到 URL
            self._state["urls"][name] = "錯誤：超時"
        except Exception as e:
            self._state["urls"][name] = f"錯誤：{e}"

    def _get_cloudflare_url(self):
        """下載並執行 Cloudflared，獲取通道 URL。"""
        name = "Cloudflare"
        try:
            if not Path('./cloudflared').exists():
                print("通道管理器: 正在下載 Cloudflared...")
                subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', 'cloudflared'], check=True)
                subprocess.run(['chmod', '+x', 'cloudflared'], check=True)

            command = ['./cloudflared', 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self._run_tunnel_service(name, command, r'(https?://\S+\.trycloudflare\.com)')
        except Exception as e:
            self._state["urls"][name] = f"錯誤：前置作業失敗 - {e}"

    def _get_localtunnel_url(self):
        """安裝並執行 Localtunnel，獲取通道 URL。"""
        name = "Localtunnel"
        try:
            # 檢查並安裝 npm 和 localtunnel
            if shutil.which('npm') is None:
                print("通道管理器: 正在安裝 Node.js 和 npm...")
                subprocess.run(['apt-get', 'install', '-qqy', 'nodejs', 'npm'], check=True, capture_output=True)
            if shutil.which('lt') is None:
                 print("通道管理器: 正在安裝 localtunnel...")
                 subprocess.run(['npm', 'install', '-g', 'localtunnel'], check=True, capture_output=True)

            # 任務 2.2：加入 --bypass-tunnel-reminder 以實現免密碼啟動
            command = ['lt', '--port', str(self.port), '--bypass-tunnel-reminder']
            self._run_tunnel_service(name, command, r'(https?://\S+\.loca\.lt)')
        except Exception as e:
            self._state["urls"][name] = f"錯誤：前置作業失敗 - {e}"

    def _get_colab_url(self):
        """使用 Colab API 獲取官方代理 URL。"""
        name = "Colab"
        try:
            if IN_COLAB:
                # Colab 的 eval_js 可能會阻塞，所以整個函式在執行緒中運行是安全的
                result = colab_output.eval_js(f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})", timeout_sec=self._timeout)
                if isinstance(result, str) and result.startswith('http'):
                    self._state["urls"][name] = result
                else:
                    self._state["urls"][name] = "錯誤：未返回有效網址"
            else:
                # 在非 Colab 環境中，模擬一個延遲和結果
                time.sleep(3)
                self._state["urls"][name] = "http://mock-colab-url.dev"

        except Exception as e:
            self._state["urls"][name] = f"錯誤：{e}"

    def start_tunnels(self):
        """並行啟動所有通道的建立程序。"""
        self._state["urls"] = {} # 初始化/重設 URLs

        racers = [
            threading.Thread(target=self._get_cloudflare_url),
            threading.Thread(target=self._get_localtunnel_url),
            threading.Thread(target=self._get_colab_url),
        ]

        for r in racers:
            r.start()
            self.threads.append(r)

    def stop_tunnels(self):
        """停止所有由通道管理器啟動的子程序。"""
        print("通道管理器: 正在停止所有通道服務...")
        for p in self.processes:
            if p.poll() is None:
                # 使用 terminate() 而不是 kill() 來更優雅地關閉
                p.terminate()

        # 等待執行緒結束 (雖然它們應該在超時或成功後就退出了)
        for t in self.threads:
            t.join(timeout=1)

# --- 主啟動函式 ---
def launch():
    """完整的應用程式啟動程序。"""
    shared_state = {
        "server_status": "未啟動",
        "urls": {},
        "stop_all": threading.Event(),
        "all_done": False,
    }

    server_proc = None
    tunnel_manager = None

    try:
        # 步驟 1: 在背景啟動後端伺服器
        shared_state["server_status"] = "正在啟動中..."
        # 假設 src.core.mini_server 會監聽 8000 埠號
        app_port = 8000
        server_command = [sys.executable, "-m", "src.core.mini_server", str(app_port)]
        server_proc = subprocess.Popen(
            server_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8'
        )
        # 簡單的延遲以等待伺服器啟動
        time.sleep(3)
        if server_proc.poll() is None:
            shared_state["server_status"] = f"✅ 運行中 (埠號: {app_port})"
        else:
            shared_state["server_status"] = f"❌ 啟動失敗 (返回碼: {server_proc.poll()})"
            _build_and_print_ui(shared_state)
            return # 伺服器啟動失敗，直接退出

        # 步驟 2: 啟動通道
        tunnel_manager = TunnelManager(app_port, shared_state)
        tunnel_manager.start_tunnels()

        # 步驟 3: 進入 UI 刷新迴圈
        while len(shared_state["urls"]) < len(TUNNEL_ORDER):
            if server_proc.poll() is not None:
                shared_state["server_status"] = f"❌ 已停止 (返回碼: {server_proc.poll()})"
                break # 伺服器意外終止，跳出 UI 迴圈

            _build_and_print_ui(shared_state)
            time.sleep(UI_REFRESH_SECONDS)

        shared_state["all_done"] = True
        _build_and_print_ui(shared_state) # 顯示最終的 UI

        print("\n---")
        print("主服務正在背景運行。關閉此 Colab 儲存格或執行中斷指令以終止所有服務。")

        # 保持主執行緒活躍，以監控後端服務狀態
        while not shared_state["stop_all"].is_set():
            if server_proc.poll() is not None:
                print(f"\n\n🚨 偵測到後端服務意外終止 (返回碼: {server_proc.poll()})。")
                shared_state["server_status"] = "❌ 已停止"
                # 不再刷新 UI，僅打印錯誤並退出監控
                break
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n收到使用者中斷指令，正在優雅地關閉所有服務...")
    except Exception as e:
        print(f"\n\n啟動器發生致命錯誤: {e}")
    finally:
        shared_state["stop_all"].set()
        if tunnel_manager:
            tunnel_manager.stop_tunnels()
        if server_proc and server_proc.poll() is None:
            print("正在終止後端伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)
        print("所有服務已關閉。")


def prepare_dependencies():
    """
    檢查並解壓縮 `dependencies.tar.gz`，將其路徑注入 `sys.path`。
    (此函式內容來自舊的 main 函式)
    """
    deps_archive_path = "dependencies.tar.gz"
    if not os.path.exists(deps_archive_path):
        print(f"錯誤：依賴壓縮檔 '{deps_archive_path}' 不存在。", file=sys.stderr)
        sys.exit(1)

    deps_path = tempfile.mkdtemp(prefix="baked_deps_")

    try:
        with tarfile.open(deps_archive_path, "r:gz") as tar:
            tar.extractall(path=deps_path)
    except (tarfile.TarError, IOError) as e:
        print(f"錯誤：解壓縮 '{deps_archive_path}' 時發生嚴重錯誤: {e}", file=sys.stderr)
        shutil.rmtree(deps_path)
        sys.exit(1)

    sys.path.insert(0, deps_path)
    print(f"✅ 依賴已成功注入: {deps_path}")
    return True


if __name__ == "__main__":
    # Colab 環境的啟動流程
    # 1. 準備依賴
    prepare_dependencies()
    # 2. 啟動所有服務
    launch()
