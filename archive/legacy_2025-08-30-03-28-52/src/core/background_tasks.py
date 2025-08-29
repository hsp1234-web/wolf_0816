import asyncio
import sys
from pathlib import Path
import logging
import subprocess
import os

# --- 標準日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- 基本設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
VENV_DIR = ROOT_DIR / "venvs"

background_processes = []

async def run_subprocess_for_install(command, **kwargs):
    log.debug(f"執行安裝指令: {' '.join(str(c) for c in command)}")
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.error(f"❌ 指令執行失敗。返回碼: {proc.returncode}")
        log.error(f"   [stdout]:\n{stdout.decode('utf-8', 'ignore')}")
        log.error(f"   [stderr]:\n{stderr.decode('utf-8', 'ignore')}")
        raise subprocess.CalledProcessError(proc.returncode, command, stdout, stderr)
    log.info("✅ 安裝指令執行成功。")
    return stdout.decode(), stderr.decode()

async def log_subprocess_output(process, name):
    # 此函式現在只用於 Huey consumer，其日誌由 Huey 自行管理，
    # 但我們仍然可以捕獲其 stdout/stderr 以進行除錯。
    while process.returncode is None:
        if process.stdout:
            stdout_line = await process.stdout.readline()
            if stdout_line:
                log.info(f"[{name}/stdout] {stdout_line.decode().strip()}")
        if process.stderr:
            stderr_line = await process.stderr.readline()
            if stderr_line:
                log.error(f"[{name}/stderr] {stderr_line.decode().strip()}")
        await asyncio.sleep(0.1)
    log.info(f"服務 '{name}' 已終止，返回碼: {process.returncode}。")

async def install_and_launch_workers():
    """
    簡化後的啟動流程。
    假設所有依賴（包括 Huey 和工作者們的）都已由 `run_app.py`
    安裝在主 Python 環境中。此函式現在只負責啟動 Huey consumer。
    """
    log.info("--- [背景任務] 開始啟動工作者 ---")
    await asyncio.sleep(1)

    python_executable = sys.executable

    try:
        log.info("正在使用當前 Python 環境啟動 Huey consumer 來運行所有工作者...")
        consumer_script = ROOT_DIR / "huey_consumer.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)

        proc = await asyncio.create_subprocess_exec(
            str(python_executable),
            str(consumer_script),
            "huey_consumer.huey",
            "--workers", "4",
            "--worker-type", "thread",
            "--verbose", # 增加 Huey 的日誌輸出以利除錯
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        background_processes.append(proc)
        log.info(f"✅ Huey consumer 已在背景啟動 (PID: {proc.pid})，管理所有工作者。")
        asyncio.create_task(log_subprocess_output(proc, "huey_consumer"))

    except Exception as e:
        log.critical(f"❌ 啟動工作者時發生致命錯誤:", exc_info=True)

    await asyncio.sleep(1)
    log.info("[背景任務] 工作者啟動流程完成。")
