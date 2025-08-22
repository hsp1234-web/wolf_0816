import asyncio
import sys
from pathlib import Path
import logging
import subprocess

# --- 基本設定 ---
# 由於此檔案被 main.py 導入，我們可以從 main.py 的視角來設定路徑
# main.py 的父目錄是 services/static_web_server/
# 我們需要往上兩層才能到達專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
VENV_DIR = ROOT_DIR / "venvs" # 使用正式的 venvs 目錄
LOG_PREFIX = "[BackgroundTask]"

# 存儲背景服務的子程序物件，防止它們被記憶體回收
background_processes = []

from workers.logging_worker import add_log

def log(level, message):
    """將日誌發送到佇列的輔助函式。"""
    # 正確的呼叫方式是不使用 .delay()
    add_log("background_tasks", level, message)

async def run_subprocess_for_install(command, **kwargs):
    """一個非同步執行子程序並等待其完成的輔助函式，用於安裝過程。"""
    log("DEBUG", f"執行安裝指令: {' '.join(command)}")
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log("ERROR", f"❌ 指令執行失敗。返回碼: {proc.returncode}")
        log("ERROR", f"   [stdout]:\n{stdout.decode('utf-8', 'ignore')}")
        log("ERROR", f"   [stderr]:\n{stderr.decode('utf-8', 'ignore')}")
        raise subprocess.CalledProcessError(proc.returncode, command, stdout, stderr)
    log("INFO", "✅ 安裝指令執行成功。")
    return stdout.decode(), stderr.decode()

import os

async def log_subprocess_output(process, name):
    """讀取子程序的輸出並加上前綴後記錄下來。"""
    while process.returncode is None:
        if process.stdout:
            stdout_line = await process.stdout.readline()
            if stdout_line:
                log("DEBUG", f"[{name}/stdout] {stdout_line.decode().strip()}")
        if process.stderr:
            stderr_line = await process.stderr.readline()
            if stderr_line:
                log("ERROR", f"[{name}/stderr] {stderr_line.decode().strip()}")
        await asyncio.sleep(0.1)
    log("INFO", f"服務 '{name}' 已終止，返回碼: {process.returncode}。")

async def install_and_launch_workers():
    """
    主要的背景任務，為所有工作者建立一個共享的虛擬環境，
    安裝它們所有的依賴，然後啟動一個 Huey consumer 來運行它們。
    """
    log("INFO", "--- [背景任務] 開始執行工作者安裝與啟動 ---")
    await asyncio.sleep(1)

    try:
        # 步驟 1: 為所有工作者建立一個統一的虛擬環境
        worker_venv_name = "workers_env"
        venv_path = VENV_DIR / worker_venv_name
        log("INFO", f"為所有工作者建立共享虛擬環境於: {venv_path}")
        await run_subprocess_for_install([sys.executable, "-m", "uv", "venv", str(venv_path)])
        python_executable = venv_path / "bin" / "python"

        # 步驟 2: 收集所有工作者和服務的依賴
        log("INFO", "正在收集所有工作者和服務的依賴...")
        all_reqs_path = ROOT_DIR / "all_workers_requirements.txt"

        # 這裡我們合併所有 requirements.txt 檔案。
        # 在一個更複雜的系統中，可能會用更精細的工具來管理依賴，
        # 但對於目前的需求，這是一個簡單有效的方法。
        req_files = list(ROOT_DIR.glob("services/*/requirements.txt"))
        req_files.extend(list(ROOT_DIR.glob("workers/requirements.txt")))

        with open(all_reqs_path, "w") as outfile:
            for req_file in req_files:
                with open(req_file) as infile:
                    outfile.write(f"# --- From {req_file.relative_to(ROOT_DIR)} ---\n")
                    outfile.write(infile.read())
                    outfile.write("\n")

        log("INFO", f"所有依賴已合併至 {all_reqs_path}")

        # 步驟 3: 在共享環境中安裝所有依賴
        log("INFO", f"在 '{worker_venv_name}' 環境中安裝所有依賴...")
        await run_subprocess_for_install([
            sys.executable, "-m", "uv", "pip", "install",
            "-r", str(all_reqs_path),
            "--python", str(python_executable)
        ])
        log("SUCCESS", "✅ 所有工作者依賴已安裝。")

        # 步驟 4: 啟動 Huey consumer
        log("INFO", "正在啟動 Huey consumer 來運行所有工作者...")
        consumer_script = ROOT_DIR / "huey_consumer.py"

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)

        proc = await asyncio.create_subprocess_exec(
            str(python_executable),
            str(consumer_script),
            "huey_consumer.huey", # 告訴 huey consumer 在哪裡找到 huey 實例
            "--workers", "4",     # 啟動 4 個執行緒/程序來並行處理任務
            "--worker-type", "thread", # 使用執行緒，因為我們的任務是 I/O 密集型
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        background_processes.append(proc)
        log("SUCCESS", f"✅ Huey consumer 已在背景啟動 (PID: {proc.pid})，管理所有工作者。")
        asyncio.create_task(log_subprocess_output(proc, "huey_consumer"))

    except Exception as e:
        log("CRITICAL", f"❌ 啟動工作者時發生致命錯誤: {e}")

    await asyncio.sleep(1)
    log("INFO", "[背景任務] 工作者啟動流程完成。")
