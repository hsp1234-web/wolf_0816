# 檔案: run_e2e_tests.py
# 說明: 獨立的端對端測試啟動器。
#      此腳本負責準備測試環境、執行測試並清理資源。
import subprocess
import sys
import asyncio
import os

async def main():
    """主函數，協調整個測試流程。"""
    server_process = None
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))
        tests_dir = os.path.join(project_root, "tests")

        # 步驟 1: 安裝所有依賴 (伺服器 + 測試)
        print("--- 正在安裝伺服器依賴 (fastapi, uvicorn)... ---", flush=True)
        server_reqs_path = os.path.join(project_root, "requirements-server.txt")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", server_reqs_path], check=True, capture_output=True)
        print("--- 伺服器依賴安裝完成 ---", flush=True)

        print("--- 正在安裝測試依賴 (playwright, pytest)... ---", flush=True)
        test_reqs_path = os.path.join(tests_dir, "requirements.txt")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", test_reqs_path], check=True, capture_output=True)
        print("--- 測試依賴安裝完成 ---", flush=True)

        # 步驟 1.1: 安裝 Playwright 瀏覽器核心
        print("--- 正在安裝 Playwright 瀏覽器核心... ---", flush=True)
        subprocess.run(
            [sys.executable, "-m", "playwright", "install"],
            check=True,
            capture_output=True,
            text=True
        )
        print("--- Playwright 瀏覽器核心安裝完成 ---", flush=True)

        # 步驟 2: 在背景啟動 API 伺服器
        print("--- 正在背景啟動 API 伺服器 (api_server_v2.py)... ---", flush=True)
        api_server_path = os.path.join(project_root, "api_server_v2.py")
        server_process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", api_server_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_root
        )

        # 步驟 2.1: 等待伺服器就緒
        print("--- 等待伺服器就緒 (最多 30 秒)... ---", flush=True)
        start_time = asyncio.get_event_loop().time()
        server_ready = False
        stderr_output = []

        while asyncio.get_event_loop().time() - start_time < 30:
            tasks = {
                'stdout': asyncio.create_task(server_process.stdout.readline()),
                'stderr': asyncio.create_task(server_process.stderr.readline())
            }
            done, pending = await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_COMPLETED)

            for p in pending:
                p.cancel()

            for task in done:
                line = task.result()
                if not line:
                    continue

                line_str = line.decode('utf-8').strip()
                if task == tasks['stdout']:
                    if line_str: print(f"[伺服器 STDOUT] {line_str}", flush=True)
                    if "Uvicorn running on" in line_str:
                        server_ready = True
                elif task == tasks['stderr']:
                    if line_str: print(f"[伺服器 STDERR] {line_str}", flush=True)
                    stderr_output.append(line_str)

            if server_ready:
                print("--- 伺服器已就緒！ ---", flush=True)
                break

        if not server_ready:
            error_message = "等待伺服器就緒時超時或串流結束。\n"
            error_message += "伺服器 STDERR 輸出:\n" + "\n".join(stderr_output)
            raise RuntimeError(error_message)

        # 步驟 3: 執行 Pytest 測試
        print("--- 正在執行 Playwright E2E 測試... ---", flush=True)
        # Pytest 會自動發現並執行 tests/test_e2e.py
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pytest", tests_dir],
            check=False,
            capture_output=True,
            text=True
        )

        # 步驟 4: 顯示測試結果
        print("\n" + "="*20 + " 測試報告 " + "="*20)
        print(result.stdout)
        if result.stderr:
            print("\n--- 測試 STDERR ---")
            print(result.stderr)
        print("="*52 + "\n")

        if result.returncode != 0:
            print("--- ❌ E2E 測試失敗 ---", flush=True)
            sys.exit(1)
        else:
            print("--- ✅ E2E 測試成功 ---", flush=True)

    except Exception as e:
        print(f"\n--- ❌ 測試啟動器發生錯誤: {e} ---")
        sys.exit(1)
    finally:
        # 步驟 5: 無論成敗，確保伺服器被終止
        if server_process and server_process.returncode is None:
            print("--- 正在關閉 API 伺服器... ---", flush=True)
            server_process.terminate()
            await server_process.wait()
            print("--- API 伺服器已關閉 ---", flush=True)

if __name__ == "__main__":
    # Windows 平台需要不同的事件迴圈策略
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
