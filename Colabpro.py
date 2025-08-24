# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v12) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "688" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
#@markdown **強制刷新後端程式碼 (FORCE_REPO_REFRESH)**
#@markdown > **如果勾選，每次執行都會先刪除舊的專案資料夾，再重新下載。**
FORCE_REPO_REFRESH = True #@param {type:"boolean"}
#@markdown ---
#@markdown ### **(2) 通用設定**
#@markdown > **此處為儀表板顯示相關的常用設定。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒)**
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **時區設定**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}
#@markdown **自動清理畫面 (ENABLE_CLEAR_OUTPUT)**
#@markdown > **勾選後，儀表板會自動刷新，介面較為清爽。取消勾選則會保留所有日誌，方便除錯。**
ENABLE_CLEAR_OUTPUT = True #@param {type:"boolean"}
#@markdown ---
#@markdown > **確認所有設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動所有程序。**
#@markdown ---

# ======================================================================================
# ==                                  開發者日誌                                  ==
# ======================================================================================
#
# 版本: 12.0 (架構: UI/邏輯分離)
# 日期: 2025-08-25T05:00:00+08:00
#
# 本次變更重點:
# 1. **架構還原**: 根據使用者最終決策，將核心協調邏輯（通道建立、UI刷新）移回 `Colabpro.py`。
# 2. **職責劃分**: `Colabpro.py` 現在負責所有 Colab 端的協調與 UI 展示。
# 3. **`run.py` 簡化**: `run.py` 被簡化為一個純粹的、阻塞式的 Web 伺服器啟動器。
#
# ======================================================================================

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import os
import shutil
import subprocess
import time
import threading
import re
from pathlib import Path
import traceback

# --- 模擬 Colab 環境 ---
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

# ==============================================================================
# PART 1: GIT 下載器功能
# ==============================================================================
def download_repository(project_folder_name, repo_url, branch):
    project_path = Path(project_folder_name)
    print(f"準備下載專案至 '{project_folder_name}'...")
    if FORCE_REPO_REFRESH and project_path.exists():
        print(f"正在強制刪除舊資料夾: {project_path}")
        shutil.rmtree(project_path)
    if project_path.exists():
        print(f"✅ 專案資料夾 '{project_path}' 已存在，跳過下載。")
        return str(project_path.resolve())
    print("🚀 開始從 Git 下載...")
    try:
        subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(project_path)],
            check=True, capture_output=True, text=True,
        )
        print("✅ 專案程式碼下載成功！")
        return str(project_path.resolve())
    except subprocess.CalledProcessError as e:
        print(f"❌ Git clone 失敗: {e.stderr}")
        return None

# ==============================================================================
# PART 2: UI 與通道管理器
# ==============================================================================
TUNNEL_ORDER = ["Cloudflare", "Localtunnel", "Colab"]

class DisplayManager:
    """ 負責管理 Colab 儲存格的純文字 UI 輸出。"""
    def __init__(self, shared_state):
        self._state = shared_state

    def print_ui(self):
        if ENABLE_CLEAR_OUTPUT:
            ipy_clear_output(wait=True)

        output = ["🚀 善狼一鍵啟動器 v12 🚀", ""]
        server_status = self._state.get("server_status", "正在初始化...")
        output.append(f"📦 後端服務: {server_status}")
        output.append("\n🔗 公開存取網址:")

        urls = self._state.get("urls", {})
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

        if self._state.get("all_done"):
            output.append("\n✅ 應用程式已就緒！")

        print("\n".join(output), flush=not ENABLE_CLEAR_OUTPUT)

class TunnelManager:
    """ 負責並行啟動和管理多個穿透通道。"""
    def __init__(self, port, shared_state, project_path, timeout=20):
        self.port = port
        self._state = shared_state
        self._project_path = Path(project_path)
        self._timeout = timeout
        self.threads = []
        self.processes = []

    def _run_tunnel_service(self, name, command, pattern, cwd):
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', cwd=cwd)
            self.processes.append(proc)
            for line in iter(proc.stdout.readline, ''):
                match = re.search(pattern, line)
                if match:
                    self._state["urls"][name] = match.group(1)
                    return
            proc.wait(timeout=self._timeout)
            if self._state["urls"].get(name) is None:
                self._state["urls"][name] = f"錯誤：程序已結束 (Code: {proc.returncode})"
        except Exception as e:
            self._state["urls"][name] = f"錯誤：{e}"

    def _get_cloudflare_url(self):
        name = "Cloudflare"
        try:
            cf_path = self._project_path / 'cloudflared'
            if not cf_path.exists():
                subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', str(cf_path)], check=True)
                subprocess.run(['chmod', '+x', str(cf_path)], check=True)
            command = [str(cf_path), 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self._run_tunnel_service(name, command, r'(https?://\S+\.trycloudflare\.com)', self._project_path)
        except Exception as e:
            self._state["urls"][name] = f"錯誤：前置作業失敗 - {e}"

    def _get_localtunnel_url(self):
        name = "Localtunnel"
        try:
            if shutil.which('lt') is None:
                print("正在安裝 localtunnel...")
                subprocess.run(['npm', 'install', '-g', 'localtunnel'], check=True, capture_output=True)
            command = ['lt', '--port', str(self.port), '--bypass-tunnel-reminder']
            self._run_tunnel_service(name, command, r'(https?://\S+\.loca\.lt)', self._project_path)
        except Exception as e:
            self._state["urls"][name] = f"錯誤：前置作業失敗 - {e}"

    def _get_colab_url(self):
        name = "Colab"
        try:
            if IN_COLAB:
                result = colab_output.eval_js(f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})", timeout_sec=self._timeout)
                self._state["urls"][name] = result if isinstance(result, str) and result.startswith('http') else "錯誤：未返回有效網址"
            else:
                time.sleep(1); self._state["urls"][name] = "http://mock-colab-url.dev"
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
        for p in self.processes:
            if p.poll() is None: p.terminate()
        for t in self.threads:
            t.join(timeout=1)

# ==============================================================================
# PART 3: 主啟動器邏輯
# ==============================================================================
def launch_application(project_path_str: str, deps_path_str: str):
    project_path = Path(project_path_str)
    shared_state = {"server_status": "未啟動", "urls": {}, "all_done": False}
    display = DisplayManager(shared_state)
    server_proc, tunnel_manager = None, None
    try:
        shared_state["server_status"] = "正在啟動中..."
        display.print_ui()

        server_command = [sys.executable, "run.py", "--deps-path", deps_path_str]
        server_proc = subprocess.Popen(server_command, cwd=project_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        app_port = None
        for line in iter(server_proc.stdout.readline, ''):
            line = line.strip()
            if line.startswith("核心啟動器："): print(line) # 轉發 run.py 的日誌
            if line.startswith("APP_PORT:"):
                app_port = int(line.split(":")[1].strip())
                shared_state["server_status"] = f"✅ 運行中 (埠號: {app_port})"
                break

        if app_port is None:
            raise RuntimeError("無法從 run.py 獲取應用程式埠號。")

        tunnel_manager = TunnelManager(app_port, shared_state, project_path)
        tunnel_manager.start_tunnels()

        while len(shared_state["urls"]) < len(TUNNEL_ORDER):
            if server_proc.poll() is not None:
                shared_state["server_status"] = f"❌ 已停止 (返回碼: {server_proc.poll()})"
                break
            display.print_ui()
            time.sleep(UI_REFRESH_SECONDS)

        shared_state["all_done"] = True
        display.print_ui()

        print("\n---\n主服務正在背景運行。關閉此 Colab 儲存格或執行中斷指令以終止所有服務。")
        server_proc.wait() # 等待後端服務結束

    except KeyboardInterrupt:
        print("\n\n收到使用者中斷指令，正在優雅地關閉所有服務...")
    except Exception:
        print(f"\n\n啟動器發生致命錯誤:")
        traceback.print_exc()
    finally:
        if tunnel_manager: tunnel_manager.stop_tunnels()
        if server_proc and server_proc.poll() is None:
            print("正在終止後端伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)
        print("所有服務已關閉。")

# ==============================================================================
# FINAL EXECUTION BLOCK
# ==============================================================================
if __name__ == '__main__':
    print("--- 善狼一鍵啟動器 ---")
    try:
        project_path = download_repository(PROJECT_FOLDER_NAME, REPOSITORY_URL, TARGET_BRANCH_OR_TAG)
        if not project_path: raise RuntimeError("專案下載失敗")

        root_dir = Path.cwd()
        deps_archive_path = root_dir / "dependencies.tar.gz"

        if not deps_archive_path.exists():
            print(f"\n⚠️ 依賴壓縮檔 '{deps_archive_path}' 不存在，正在嘗試自動建立...")
            bake_script_path = Path(project_path) / "scripts" / "bake_dependencies.sh"
            if not bake_script_path.exists(): raise FileNotFoundError(f"找不到烘烤腳本 {bake_script_path}")

            subprocess.run(["bash", str(bake_script_path)], cwd=project_path, check=True)
            generated_deps = Path(project_path) / "dependencies.tar.gz"
            if not generated_deps.exists(): raise FileNotFoundError("烘烤腳本未成功產生依賴包")

            shutil.move(str(generated_deps), str(root_dir))
            print(f"✅ 成功建立並移動依賴包至 '{deps_archive_path}'")

        launch_application(project_path, str(deps_archive_path))

    except Exception as e:
        print(f"\n--- ❌ 發生無法處理的致命錯誤 ---")
        print(f"錯誤訊息: {e}")
        traceback.print_exc()
    finally:
        print("\n--- 執行結束 ---")
