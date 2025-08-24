# -*- coding: utf-8 -*-
"""
Colab 啟動器 v2.1

此腳本為 Colab 環境的唯一入口點，整合了依賴準備、後端啟動、
多通道穿透以及動態狀態顯示的完整啟動流程。

接收來自 Colabpro.py 的參數，實現完全可配置的啟動。
"""
import os
import sys
import tarfile
import tempfile
import shutil
import subprocess
import time
import threading
import re
from pathlib import Path
import argparse

# --- 模擬 Colab 環境，方便本地測試 ---
try:
    from google.colab import output as colab_output
    from IPython.display import clear_output as ipy_clear_output
    IN_COLAB = True
except ImportError:
    class MockColabOutput:
        def eval_js(self, *args, **kwargs): return ""
    class MockDisplay:
        def clear_output(self, wait=False): print("\n--- 清除輸出 ---\n")
    colab_output = MockColabOutput()
    ipy_clear_output = MockDisplay().clear_output
    IN_COLAB = False
    print("警告：未在 Colab 環境中執行，將使用模擬的 display 功能。")

# --- 全域設定 ---
TUNNEL_ORDER = ["Cloudflare", "Localtunnel", "Colab"]

# --- UI 渲染函式 ---
def _build_and_print_ui(shared_state, args):
    """
    根據共享狀態字典，清除 Colab 輸出並重新繪製整個純文字 UI。
    """
    if args.clear_output:
        ipy_clear_output(wait=True)

    output = ["🚀 Colab 啟動器 v2.1 🚀", ""]
    server_status = shared_state.get("server_status", "正在初始化...")
    output.append(f"📦 後端服務: {server_status}")
    output.append("\n🔗 公開存取網址:")

    urls = shared_state.get("urls", {})
    all_urls_resolved = len(urls) >= len(TUNNEL_ORDER)

    for name in TUNNEL_ORDER:
        url = urls.get(name)
        if url:
            if "錯誤" in str(url):
                error_msg = f"\033[91m{url}\033[0m" if IN_COLAB else f"{url} (錯誤)"
                output.append(f"  - {name+':':<15} {error_msg}")
            else:
                 output.append(f"  - {name+':':<15} {url}")
        elif all_urls_resolved:
            output.append(f"  - {name+':':<15} (啟動失敗)")
        else:
            output.append(f"  - {name+':':<15} (正在產生...)")

    if shared_state.get("all_done"):
         output.append("\n✅ 應用程式已就緒！")

    print("\n".join(output), flush=not args.clear_output)

# --- 通道管理器 ---
class TunnelManager:
    """負責並行啟動和管理多個穿透通道。"""
    def __init__(self, port, shared_state, timeout=20):
        self.port = port
        self._state = shared_state
        self._timeout = timeout
        self.threads = []
        self.processes = []

    def _run_tunnel_service(self, name, command, pattern):
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            self.processes.append(proc)
            start_time = time.monotonic()
            for line in iter(proc.stdout.readline, ''):
                if time.monotonic() - start_time > self._timeout:
                    self._state["urls"][name] = "錯誤：超時"
                    return
                match = re.search(pattern, line)
                if match:
                    self._state["urls"][name] = match.group(1)
                    return
            # 如果迴圈結束 proc 也結束了
            proc.wait()
            if self._state["urls"].get(name) is None:
                 self._state["urls"][name] = f"錯誤：程序已結束 (Code: {proc.returncode})"
        except Exception as e:
            self._state["urls"][name] = f"錯誤：{e}"

    def _get_cloudflare_url(self):
        name = "Cloudflare"
        try:
            if not Path('./cloudflared').exists():
                subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', 'cloudflared'], check=True)
                subprocess.run(['chmod', '+x', 'cloudflared'], check=True)
            command = ['./cloudflared', 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self._run_tunnel_service(name, command, r'(https?://\S+\.trycloudflare\.com)')
        except Exception as e:
            self._state["urls"][name] = f"錯誤：前置作業失敗 - {e}"

    def _get_localtunnel_url(self):
        name = "Localtunnel"
        try:
            if shutil.which('npm') is None:
                subprocess.run(['apt-get', 'install', '-qqy', 'nodejs', 'npm'], check=True, capture_output=True)
            if shutil.which('lt') is None:
                 subprocess.run(['npm', 'install', '-g', 'localtunnel'], check=True, capture_output=True)
            command = ['lt', '--port', str(self.port), '--bypass-tunnel-reminder']
            self._run_tunnel_service(name, command, r'(https?://\S+\.loca\.lt)')
        except Exception as e:
            self._state["urls"][name] = f"錯誤：前置作業失敗 - {e}"

    def _get_colab_url(self):
        name = "Colab"
        try:
            if IN_COLAB:
                result = colab_output.eval_js(f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})", timeout_sec=self._timeout)
                self._state["urls"][name] = result if isinstance(result, str) and result.startswith('http') else "錯誤：未返回有效網址"
            else:
                time.sleep(3)
                self._state["urls"][name] = "http://mock-colab-url.dev"
        except Exception as e:
            self._state["urls"][name] = f"錯誤：{e}"

    def start_tunnels(self):
        self._state["urls"] = {}
        racers = [
            threading.Thread(target=self._get_cloudflare_url),
            threading.Thread(target=self._get_localtunnel_url),
            threading.Thread(target=self._get_colab_url),
        ]
        for r in racers:
            r.start()
            self.threads.append(r)

    def stop_tunnels(self):
        print("通道管理器: 正在停止所有通道服務...")
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
        for t in self.threads:
            t.join(timeout=1)

# --- 主啟動函式 ---
def launch(args):
    shared_state = {"server_status": "未啟動", "urls": {}, "stop_all": threading.Event(), "all_done": False}
    server_proc, tunnel_manager = None, None
    try:
        shared_state["server_status"] = "正在啟動中..."
        app_port = 8000
        server_command = [sys.executable, "-m", "src.core.mini_server", str(app_port)]
        server_proc = subprocess.Popen(server_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        time.sleep(3)
        if server_proc.poll() is not None:
            shared_state["server_status"] = f"❌ 啟動失敗 (返回碼: {server_proc.poll()})"
            _build_and_print_ui(shared_state, args)
            return
        shared_state["server_status"] = f"✅ 運行中 (埠號: {app_port})"

        tunnel_manager = TunnelManager(app_port, shared_state)
        tunnel_manager.start_tunnels()

        while len(shared_state["urls"]) < len(TUNNEL_ORDER):
            if server_proc.poll() is not None:
                shared_state["server_status"] = f"❌ 已停止 (返回碼: {server_proc.poll()})"
                break
            _build_and_print_ui(shared_state, args)
            time.sleep(args.refresh_rate)

        shared_state["all_done"] = True
        _build_and_print_ui(shared_state, args)

        print("\n---\n主服務正在背景運行。關閉此 Colab 儲存格或執行中斷指令以終止所有服務。")
        while not shared_state["stop_all"].is_set():
            if server_proc.poll() is not None:
                print(f"\n\n🚨 偵測到後端服務意外終止 (返回碼: {server_proc.poll()})。")
                shared_state["server_status"] = "❌ 已停止"
                break
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\n收到使用者中斷指令，正在優雅地關閉所有服務...")
    except Exception as e:
        print(f"\n\n啟動器發生致命錯誤: {e}")
    finally:
        shared_state["stop_all"].set()
        if tunnel_manager: tunnel_manager.stop_tunnels()
        if server_proc and server_proc.poll() is None:
            print("正在終止後端伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)
        print("所有服務已關閉。")

def prepare_dependencies(deps_archive_path_str):
    """
    檢查並解壓縮指定的 `dependencies.tar.gz`，將其路徑注入 `sys.path`。
    """
    deps_archive_path = Path(deps_archive_path_str)
    if not deps_archive_path.is_file():
        print(f"錯誤：依賴壓縮檔 '{deps_archive_path}' 不存在或不是一個檔案。", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="Colab 啟動器 v2.1")
    parser.add_argument("--deps-path", required=True, help="預先烘烤的依賴壓縮檔 (dependencies.tar.gz) 的絕對路徑。")
    parser.add_argument("--refresh-rate", type=float, default=0.5, help="UI 刷新頻率（秒）。")
    parser.add_argument("--timezone", type=str, default="Asia/Taipei", help="用於顯示日誌的時區。")
    parser.add_argument("--no-clear-output", action="store_false", dest="clear_output", help="停用自動清除輸出功能，方便除錯。")

    args = parser.parse_args()

    # 步驟 1: 準備依賴
    if prepare_dependencies(args.deps_path):
        # 步驟 2: 啟動所有服務
        # (時區參數暫時未在 UI 中使用，但已準備好)
        launch(args)
