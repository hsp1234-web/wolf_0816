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
    log.info("--- [背景任務] 開始執行工作者安裝與啟動 ---")
    await asyncio.sleep(1)

    is_test_mode = os.environ.get("APP_ENV") == "test"
    python_executable = sys.executable

    try:
        if is_test_mode:
            log.info("🧪 偵測到測試模式，將跳過虛擬環境建立和依賴安裝。")
        else:
            worker_venv_name = "workers_env"
            venv_path = VENV_DIR / worker_venv_name
            log.info(f"為所有工作者建立共享虛擬環境於: {venv_path}")
            await run_subprocess_for_install([sys.executable, "-m", "uv", "venv", str(venv_path)])

            if sys.platform == "win32":
                python_executable = venv_path / "Scripts" / "python.exe"
            else:
                python_executable = venv_path / "bin" / "python"

            log.info("正在收集所有工作者和服務的依賴...")
            all_reqs_path = ROOT_DIR / "all_workers_requirements.txt"

            req_files = list(ROOT_DIR.glob("services/*/requirements.txt"))
            req_files.extend(list(ROOT_DIR.glob("workers/requirements.txt")))
            req_files = [f for f in req_files if 'api_gateway' not in str(f)]

            with open(all_reqs_path, "w") as outfile:
                for req_file in req_files:
                    with open(req_file) as infile:
                        outfile.write(f"# --- From {req_file.relative_to(ROOT_DIR)} ---\n")
                        outfile.write(infile.read())
                        outfile.write("\n")

            log.info(f"所有依賴已合併至 {all_reqs_path}")

            log.info(f"在 '{worker_venv_name}' 環境中安裝所有依賴...")
            await run_subprocess_for_install([
                sys.executable, "-m", "uv", "pip", "install",
                "-r", str(all_reqs_path),
                "--python", str(python_executable)
            ])
            log.info("✅ 所有工作者依賴已安裝。")

        log.info("正在啟動 Huey consumer 來運行所有工作者...")
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
