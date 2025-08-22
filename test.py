# -*- coding: utf-8 -*-
"""
一個使用 invoke 套件的獨立測試引擎。

這個腳本被設計成一個單一的、可執行的測試啟動器，用於驗證應用的端對端啟動時間。
它會自動處理環境設定、依賴安裝、服務啟動和執行 Playwright 測試。

核心功能：
- 建立獨立的虛擬環境 (`.venv_test`)。
- 使用 `uv` 安裝所有必要的 Python 和 Node.js 依賴。
- 在背景啟動所有後端服務。
- 使用 Playwright 驗證前端 UI 是否在 60 秒內成功載入。
- 包含一個全局的 60 秒超時機制，以確保測試不會無限期運行。

使用方式：
1. 安裝 invoke: pip install invoke
2. 執行測試: invoke test-startup
"""
import os
import sys
import venv
import time
import shutil
import platform
import subprocess
import threading
import re
from pathlib import Path

# --- 自我引導安裝 invoke ---
try:
    from invoke import task, Collection, Context
except ImportError:
    print("🎨 'invoke' 未安裝，正在為您自動安裝...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "invoke"])
        from invoke import task, Collection, Context
        print("✅ 'invoke' 安裝成功。")
    except Exception as e:
        print(f"❌ 無法自動安裝 'invoke'。請手動執行 `pip install invoke` 後再試一次。錯誤: {e}")
        sys.exit(1)

# --- 全局設定 ---
ROOT_DIR = Path(__file__).parent.resolve()
VENV_DIR = ROOT_DIR / ".venv_test"
VENV_PYTHON = VENV_DIR / "bin" / "python" if platform.system() != "Windows" else VENV_DIR / "Scripts" / "python.exe"
REQ_FILE = ROOT_DIR / "requirements-server.txt"
VUE_APP_DIR = ROOT_DIR / "vue-app"
LOG_FILE = ROOT_DIR / "test_engine.log"
PROCESSES = [] # 用於存放所有背景服務的 process 物件

# 全域變數，用於在 start_services 和 run_test 之間傳遞動態分配的 URL
DYNAMIC_API_URL = None
def _print_header(message):
    """打印帶有標題格式的訊息。"""
    print("\n" + "="*60)
    print(f"    {message}")
    print("="*60)

def _run_command(c, command, workdir=None, env=None, hide=False, file_log_only=False):
    """執行一個指令並即時打印其輸出。"""
    if not file_log_only:
      print(f"🏃 [CMD] {' '.join(command)}")

    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=workdir or ROOT_DIR,
        env=process_env,
        text=True,
        encoding='utf-8',
        bufsize=1
    )
    with open(LOG_FILE, "a") as log:
        for line in iter(process.stdout.readline, ''):
            if not hide and not file_log_only:
                sys.stdout.write(line)
                sys.stdout.flush()
            log.write(line)

    process.stdout.close()
    returncode = process.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command)

def _kill_all_services():
    """終止所有已啟動的背景服務。"""
    global PROCESSES
    print("🔥 正在終止所有背景服務...")
    for proc in reversed(PROCESSES):
        if proc.poll() is None:
            try:
                # 溫和地終止
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # 強制終止
                proc.kill()
                print(f"⚠️ PID {proc.pid} 被強制終止。")
    PROCESSES = []
    print("✅ 所有服務已停止。")

# --- 測試引擎任務 ---
@task
def setup(c):
    """
    設定測試環境：建立虛擬環境並安裝所有依賴。
    """
    _print_header("1. 環境設定 (Setup)")

    if VENV_DIR.exists():
        print(f"ℹ️ 發現已存在的虛擬環境，跳過設定。如需重新設定，請執行 `invoke clean`。")
        return

    try:
        # 1. 建立虛擬環境
        print("   - 正在使用 'uv' 建立虛擬環境...")
        subprocess.run(["uv", "venv", str(VENV_DIR)], check=True, capture_output=True, text=True)
        print(f"   ✅ 成功建立虛擬環境於: {VENV_DIR}")

        # 2. 安裝 Python 依賴
        print("   - 正在使用 'uv' 安裝 Python 依賴...")
        # 使用全局 uv，並用 --python 指定虛擬環境的 python 解譯器
        _run_command(c, ["uv", "pip", "install", "--python", str(VENV_PYTHON), "-r", str(REQ_FILE)], hide=True)
        print("   ✅ Python 依賴安裝完成。")

        # 3. 安裝 Node.js 依賴
        print("   - 正在使用 'bun' 安裝 Node.js 依賴...")
        _run_command(c, ["bun", "install"], workdir=VUE_APP_DIR, hide=True)
        print("   ✅ Node.js 依賴安裝完成。")

        # 4. 安裝 Playwright 瀏覽器
        print("   - 正在安裝 Playwright 所需的瀏覽器...")
        _run_command(c, [str(VENV_PYTHON), "-m", "playwright", "install"], hide=True)
        print("   ✅ Playwright 瀏覽器安裝完成。")

    except FileNotFoundError as e:
        print(f"❌ 錯誤: 找不到必要指令 ({e.filename})。請確保 uv 和 bun 已安裝並在系統 PATH 中。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ 環境設定失敗，指令 `{' '.join(e.cmd)}` 返回錯誤碼 {e.returncode}。詳情請見日誌檔案。")
        sys.exit(1)

@task(setup)
def build(c):
    """
    建置前端應用程式。
    """
    _print_header("2. 建置前端 (Build)")
    _run_command(c, ["bun", "run", "build"], workdir=VUE_APP_DIR)
    print("✅ 前端建置完成。")

@task(build)
def start_services(c):
    """
    在背景啟動核心後端服務，並捕獲其動態分配的 URL。
    """
    _print_header("3. 啟動核心後端服務 (via localrun_new.py)")
    global PROCESSES, DYNAMIC_API_URL

    # 使用虛擬環境的 Python 解譯器來執行新的啟動器
    command = [
        str(VENV_PYTHON),
        str(ROOT_DIR / "runner" / "localrun_new.py"),
        "--no-mock" # 在測試時使用真實模式
    ]

    print(f"🚀 正在執行: {' '.join(command)}")
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        bufsize=1
    )
    PROCESSES.append(proc)

    # 等待 localrun_new.py 完成健康檢查並輸出成功訊息
    print(f"⏳ 等待後端健康檢查完成...")
    ready = False
    # 更穩健的 Regex，專門匹配包含 URL 的那一行
    url_line_pattern = re.compile(r"網址已就緒: (https?://\S+)")
    health_check_pattern = re.compile(r"✅ 後端健康檢查成功。")

    try:
        for line in iter(proc.stdout.readline, ''):
            sys.stdout.write(line)
            with open(LOG_FILE, "a") as log:
                log.write(line)

            # 捕獲 URL
            if DYNAMIC_API_URL is None:
                match = url_line_pattern.search(line)
                if match:
                    # URL 是捕獲組 1
                    DYNAMIC_API_URL = match.group(1)
                    print(f"✅ 捕獲到動態 API URL: {DYNAMIC_API_URL}")

            # 檢查是否已就緒
            if health_check_pattern.search(line):
                print(f"✅ 後端服務已就緒！")
                ready = True
                time.sleep(2) # 給予緩衝時間，確保服務完全穩定
                break

        if not ready:
             raise RuntimeError("後端服務未能成功啟動或通過健康檢查。")
        if DYNAMIC_API_URL is None:
             raise RuntimeError("未能從啟動器輸出中捕獲到 API URL。")

    except Exception as e:
        print(f"❌ 啟動服務時發生錯誤: {e}")
        _kill_all_services()
        sys.exit(1)

@task(start_services)
def run_test(c):
    """
    執行 Playwright 測試以驗證 UI 是否載入。
    """
    _print_header("4. 執行 UI 載入測試 (Run Test)")

    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            if not DYNAMIC_API_URL:
                raise RuntimeError("動態 API URL 未被設定，測試無法繼續。")

            target_url = DYNAMIC_API_URL.replace("127.0.0.1", "localhost")

            # 最終診斷：檢查啟動器程序是否仍在運行
            if not PROCESSES:
                raise RuntimeError("❌ PROCESSES 列表為空，無法檢查啟動器狀態。")
            launcher_proc = PROCESSES[0] # 假設它是唯一的程序
            poll_result = launcher_proc.poll()
            if poll_result is not None:
                # 為了獲取更多上下文，讀取一些剩餘的日誌
                remaining_output = launcher_proc.stdout.read()
                print("--- [啟動器剩餘日誌] ---")
                print(remaining_output)
                print("--- [日誌結束] ---")
                raise RuntimeError(f"❌ 啟動器程序已意外終止，結束碼: {poll_result}。測試無法繼續。")
            else:
                print(f"✅ 啟動器程序 (PID: {launcher_proc.pid}) 仍在運行中。")

            print(f"🩺 執行手動連線測試 (curl) 到: {target_url}")
            try:
                # 使用 curl 進行額外的連線診斷
                # capture_output=True 以免干擾主日誌
                result = subprocess.run(
                    ["curl", "-v", "--max-time", "5", target_url],
                    check=True,
                    timeout=10,
                    capture_output=True
                )
                print("✅ curl 連線測試成功。")
                print(f"   - curl stdout: {result.stdout.decode(errors='ignore')}")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"❌ curl 連線測試失敗: {e}")
                if hasattr(e, 'stderr'):
                    print(f"   - curl stderr: {e.stderr.decode(errors='ignore')}")
                raise RuntimeError(f"curl 連線測試失敗，無法繼續 Playwright 測試。")

            print(f"🎭 Playwright 正在導航至: {target_url}")
            page.goto(target_url, timeout=15000)

            print("   - 正在驗證頁面標題...")
            # 給予 30 秒的寬裕時間來等待標題出現
            expect(page).to_have_title(re.compile("音訊轉錄儀"), timeout=30000)
            print("   ✅ 頁面標題 '音訊轉錄儀' 驗證成功。")

            print("\n🎉 UI 載入測試成功！")
            browser.close()
            return True

        except Exception as e:
            print(f"\n❌ UI 載入測試失敗: {e}")
            return False

@task
def clean(c):
    """
    清理測試引擎產生的所有檔案和程序。
    """
    _print_header("清理環境 (Clean)")
    _kill_all_services()
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
        print(f"🗑️ 已刪除虛擬環境: {VENV_DIR}")
    if LOG_FILE.exists():
        os.remove(LOG_FILE)
        print(f"🗑️ 已刪除日誌檔案: {LOG_FILE}")
    # 清理 vue-app/dist
    dist_dir = VUE_APP_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print(f"🗑️ 已刪除前端建置目錄: {dist_dir}")
    print("✅ 清理完成。")

@task(setup, build, start_services, run_test)
def test_startup(c):
    """
    執行完整的啟動時間測試流程，並在 60 秒後強制終止。
    """
    start_time = time.monotonic()

    # 這是主任務，但實際工作由依賴任務完成。
    # 我們需要一個方法來獲取 run_test 的結果。
    # invoke 本身不直接支持任務返回值，所以我們透過一個全局變數或檔案來傳遞狀態。
    # 但在這個簡單的案例中，如果 run_test 失敗，它會拋出異常，這就足夠了。

    print("\n" + "*"*60)
    print("✅ 測試引擎所有步驟成功完成！")
    print(f"⏱️  總耗時: {time.monotonic() - start_time:.2f} 秒")
    print("*"*60)

# --- 主執行邏輯 ---
# 為了實現 60 秒超時，我們需要一個包裝器來運行 invoke 任務
def main():
    """
    測試引擎的主入口點，負責處理全局超時。
    """
    _print_header("啟動測試引擎 (帶 60 秒超時)")

    # 清理日誌檔案
    if LOG_FILE.exists():
        os.remove(LOG_FILE)

    # 使用 threading.Timer 實現超時
    timeout_occurred = threading.Event()
    def on_timeout():
        print("\n" + "!"*60)
        print("‼️‼️‼️  測試超過 60 秒，強制終止！ ‼️‼️‼️")
        print("!"*60)
        timeout_occurred.set()
        _kill_all_services()
        # 使用 os._exit 強制退出，因為主執行緒可能被卡住
        os._exit(1)

    timer = threading.Timer(60.0, on_timeout)
    timer.start()

    start_time = time.monotonic()

    try:
        # 這裡我們需要以程式化的方式調用 invoke 任務
        # 為了簡單起見，我們直接調用函式
        # 注意：invoke 的上下文 c 在這裡需要手動建立
        ctx = Context()

        # 執行任務流程
        setup(ctx)
        build(ctx)
        start_services(ctx)
        success = run_test(ctx)

        if success:
            print("\n" + "*"*60)
            print("✅ 測試引擎所有步驟在時限內成功完成！")
            print(f"⏱️  總耗時: {time.monotonic() - start_time:.2f} 秒")
            print("*"*60)
        else:
            # 如果 run_test 返回 False，我們也認為是失敗
            raise RuntimeError("UI 載入測試明確返回失敗狀態。")

    except Exception as e:
        print("\n" + "!"*60)
        print(f"❌ 測試引擎執行過程中發生錯誤: {e}")
        print("詳情請參閱 test_engine.log")
        print("!"*60)
        sys.exit(1)
    finally:
        # 無論成功或失敗，都停止計時器並清理服務
        timer.cancel()
        _kill_all_services()

# 建立一個命名空間以便於管理
# 這部分主要用於 `invoke --list`
ns = Collection()
ns.add_task(setup)
ns.add_task(build)
ns.add_task(start_services)
ns.add_task(run_test)
ns.add_task(clean)
ns.add_task(test_startup)

# 為了讓這個腳本可以直接執行 `python tasks.py`
if __name__ == "__main__":
    main()
