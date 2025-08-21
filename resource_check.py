import psutil
import subprocess
import shutil

def get_size(bytes, suffix="B"):
    """
    Scale bytes to its proper format e.g:
    1253656 => '1.20MB'
    1253656678 => '1.17GB'
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def assess_resources():
    print("="*10, "系統資源評估", "="*10)

    # 1. CPU 資訊
    print("\n--- CPU ---")
    try:
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        cpu_usage = psutil.cpu_percent(interval=1)
        print(f"邏輯核心數: {cpu_count_logical}")
        print(f"實體核心數: {cpu_count_physical}")
        print(f"目前使用率: {cpu_usage}%")
    except Exception as e:
        print(f"無法獲取 CPU 資訊: {e}")

    # 2. 記憶體 (RAM) 資訊
    print("\n--- 記憶體 (RAM) ---")
    try:
        svmem = psutil.virtual_memory()
        print(f"總容量: {get_size(svmem.total)}")
        print(f"可用: {get_size(svmem.available)}")
        print(f"已使用: {get_size(svmem.used)}")
        print(f"使用率: {svmem.percent}%")
    except Exception as e:
        print(f"無法獲取記憶體資訊: {e}")

    # 3. 磁碟空間資訊
    print("\n--- 磁碟空間 (/) ---")
    try:
        total, used, free = shutil.disk_usage("/")
        print(f"總容量: {get_size(total)}")
        print(f"已使用: {get_size(used)}")
        print(f"可用空間: {get_size(free)}")
    except Exception as e:
        print(f"無法獲取磁碟空間資訊: {e}")

    # 4. GPU 資訊
    print("\n--- GPU ---")
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=gpu_name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, check=True, encoding='utf-8'
        )
        gpu_info = result.stdout.strip()
        if gpu_info:
            print("偵測到 NVIDIA GPU:")
            print(gpu_info)
        else:
            print("未偵測到 NVIDIA GPU。")
    except FileNotFoundError:
        print("未安裝 nvidia-smi，無法偵測 NVIDIA GPU。")
    except subprocess.CalledProcessError as e:
        print(f"執行 nvidia-smi 失敗: {e.stderr}")
    except Exception as e:
        print(f"獲取 GPU 資訊時發生未知錯誤: {e}")

    print("\n" + "="*35)

if __name__ == "__main__":
    # 需要先安裝 psutil
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "psutil"], check=True)
    except Exception as e:
        print(f"無法安裝 psutil，評估中止。錯誤: {e}")
    import sys
    assess_resources()
