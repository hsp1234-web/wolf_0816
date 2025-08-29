import asyncio
import sys
import os
import re

async def main():
    """
    啟動 api_server_v2.py，並從 uvicorn 的日誌中解析出埠號。
    這是一個臨時的驗證腳本。
    """
    print("--- 臨時啟動器 v2：開始驗證 api_server_v2.py ---")

    # 使用與目前環境相同的 Python 解譯器，-u 參數確保輸出不被緩衝
    python_executable = sys.executable
    server_script = "api_server_v2.py"

    if not os.path.exists(server_script):
        print(f"錯誤：找不到伺服器腳本 '{server_script}'")
        sys.exit(1)

    # uvicorn 將日誌輸出到 stderr
    process = await asyncio.create_subprocess_exec(
        python_executable,
        "-u", # 使用無緩衝的 stdout/stderr
        server_script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    print(f"已啟動伺服器子程序，PID: {process.pid}。等待 uvicorn 啟動日誌...")

    port_found = False
    try:
        # 循環讀取 stderr 的每一行，並為每一次讀取設置超時
        while True:
            line_bytes = await asyncio.wait_for(process.stderr.readline(), timeout=100.0)

            if not line_bytes: # 如果讀取到空字節，表示串流結束
                print("\n❌ 驗證失敗：伺服器 stderr 串流在找到埠號前回報結束。")
                break

            line = line_bytes.decode().strip()
            print(f"[SERVER LOG] {line}") # 打印日誌以供除錯

            # 使用正規表示式尋找埠號
            match = re.search(r"Uvicorn running on .*:(\d+)", line)
            if match:
                port = match.group(1)
                print(f"\n✅ 驗證成功！從日誌中解析到伺服器埠號: {port}")
                print("--- 臨時啟動器：驗證通過 ---\n")
                port_found = True
                break # 找到埠號，跳出循環

    except asyncio.TimeoutError:
        print("\n❌ 驗證失敗：在 100 秒內未收到任何伺服器日誌輸出。")
    except Exception as e:
        print(f"\n❌ 驗證期間發生未預期的錯誤: {e}")
    finally:
        if process.returncode is None:
            print(f"正在終止子程序 PID: {process.pid}...")
            process.terminate()
            await process.wait()
            print("子程序已終止。")

        if not port_found:
             print("最終狀態：失敗。")
             sys.exit(1) # 如果最終沒有找到埠號，則以失敗狀態碼退出


if __name__ == "__main__":
    asyncio.run(main())
