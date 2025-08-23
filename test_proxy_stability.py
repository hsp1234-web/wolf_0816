import subprocess
import sys
import time
import threading
import re
import os
import shutil
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict

# --- 基本設定 ---
TEST_ROUNDS = 10
REQUEST_TIMEOUT_SECONDS = 15
TARGET_PORT = 8123 # 使用一個固定的測試埠號

def log(level, message):
    """一個簡單的日誌記錄器，用於在控制台輸出彩色訊息。"""
    colors = {"SUCCESS": "\033[92m", "WARN": "\033[93m", "FAIL": "\033[91m", "INFO": "\033[94m", "RUN": "\033[96m"}
    reset = "\033[0m"
    print(f"{colors.get(level, '')}[{level:^7}] {message}{reset}")

# --- 輔助工具 ---

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    """一個極簡的 HTTP 伺服器，僅回應 200 OK。"""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        return # 禁用預設的請求日誌

class StoppableHTTPServer(HTTPServer):
    """可停止的 HTTP 伺服器版本。"""
    def run(self):
        self.serve_forever()
    def stop(self):
        threading.Thread(target=self.shutdown, daemon=True).start()

# --- 代理測試函式 ---

def test_localtunnel():
    """測試 localtunnel 的穩定性。"""
    method_name = "localtunnel"
    proc = None
    start_time = time.monotonic()
    try:
        # 確保 npm 和 localtunnel 已安裝
        if shutil.which('npm') is None:
            raise FileNotFoundError("npm 未安裝")
        if shutil.which('lt') is None:
            log("INFO", "首次運行，正在安裝 localtunnel...")
            subprocess.run(['npm', 'install', '-g', 'localtunnel'], check=True, capture_output=True)

        cmd = ['lt', '--port', str(TARGET_PORT)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        # 在時限內尋找 URL
        while time.monotonic() - start_time < REQUEST_TIMEOUT_SECONDS:
            line = proc.stdout.readline()
            if not line: break
            match = re.search(r'(https?://\S+\.loca\.lt)', line)
            if match:
                duration = time.monotonic() - start_time
                return {"success": True, "url": match.group(1), "duration": duration, "error": None}
            time.sleep(0.1)

        # 如果超時
        duration = time.monotonic() - start_time
        return {"success": False, "url": None, "duration": duration, "error": "超時"}
    except Exception as e:
        duration = time.monotonic() - start_time
        return {"success": False, "url": None, "duration": duration, "error": str(e)}
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait()

def test_cloudflare():
    """測試 Cloudflare Tunnel 的穩定性。"""
    method_name = "Cloudflare Tunnel"
    proc = None
    start_time = time.monotonic()
    try:
        # 確保 cloudflared 已安裝
        if not Path('./cloudflared').exists():
            log("INFO", "首次運行，正在下載 Cloudflared...")
            subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', 'cloudflared'], check=True)
            subprocess.run(['chmod', '+x', 'cloudflared'], check=True)

        cmd = ['./cloudflared', 'tunnel', '--url', f'http://127.0.0.1:{TARGET_PORT}']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        # 在時限內尋找 URL
        while time.monotonic() - start_time < REQUEST_TIMEOUT_SECONDS:
            line = proc.stdout.readline()
            if not line: break
            match = re.search(r'(https?://\S+\.trycloudflare\.com)', line)
            if match:
                duration = time.monotonic() - start_time
                return {"success": True, "url": match.group(1), "duration": duration, "error": None}
            time.sleep(0.1)

        # 如果超時
        duration = time.monotonic() - start_time
        return {"success": False, "url": None, "duration": duration, "error": "超時"}
    except Exception as e:
        duration = time.monotonic() - start_time
        return {"success": False, "url": None, "duration": duration, "error": str(e)}
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait()

# --- 主執行程序 ---

def run_stability_test():
    """執行完整的穩定性測試流程。"""
    log("INFO", f"啟動一個測試伺服器在 http://127.0.0.1:{TARGET_PORT}")
    server = StoppableHTTPServer(("127.0.0.1", TARGET_PORT), SimpleHTTPRequestHandler)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    time.sleep(1)

    test_targets = {
        "Localtunnel": test_localtunnel,
        "Cloudflare Tunnel": test_cloudflare,
    }

    results = defaultdict(list)

    try:
        for name, test_func in test_targets.items():
            log("RUN", f"===== 開始測試 {name} (共 {TEST_ROUNDS} 輪) =====")
            for i in range(TEST_ROUNDS):
                log("INFO", f"  -> 第 {i+1}/{TEST_ROUNDS} 輪...")
                result = test_func()
                results[name].append(result)
                status_log = "✅ 成功" if result["success"] else f"❌ 失敗 ({result['error']})"
                log("INFO", f"     結果: {status_log}, 耗時: {result['duration']:.2f} 秒")
                time.sleep(2) # 在每輪之間短暫休息，避免被服務商限速
            log("RUN", f"===== {name} 測試完成 =====\n")

        # --- 產生報告 ---
        print("\n" + "="*60)
        log("INFO", "📊 代理方案穩定性測試總結報告")
        print("="*60)
        for name, res_list in results.items():
            successes = [r for r in res_list if r["success"]]
            failures = [r for r in res_list if not r["success"]]
            success_rate = (len(successes) / len(res_list)) * 100

            avg_duration = 0
            if successes:
                avg_duration = sum(r['duration'] for r in successes) / len(successes)

            print(f"\n--- 方案: {name} ---")
            log("SUCCESS", f"  成功率: {success_rate:.1f}% ({len(successes)}/{len(res_list)})")
            log("FAIL",    f"  失敗次數: {len(failures)}")
            log("INFO",    f"  平均成功耗時: {avg_duration:.2f} 秒")
            if failures:
                log("WARN", "  失敗原因摘要:")
                error_counts = defaultdict(int)
                for f in failures:
                    error_counts[f['error']] += 1
                for error, count in error_counts.items():
                    print(f"    - {error}: {count} 次")
        print("\n" + "="*60)

    except KeyboardInterrupt:
        log("WARN", "偵測到手動中斷...")
    finally:
        log("INFO", "正在執行清理程序...")
        if Path('./cloudflared').exists():
            Path('./cloudflared').unlink()
            log("INFO", "已刪除 cloudflared 二進位檔案。")
        log("INFO", "正在關閉測試伺服器...")
        server.stop()
        server_thread.join(timeout=2)
        log("SUCCESS", "所有程序已成功關閉。")

if __name__ == "__main__":
    # 為了在 Colab 中運行，需要手動處理路徑問題
    from pathlib import Path
    os.chdir(Path(__file__).parent.resolve())
    run_stability_test()
