# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "cowsay==6.1"
# ]
# ///

import time
import sys
import cowsay

print("🐮 Worker A: 啟動中...", flush=True)

try:
    while True:
        cowsay.cow("Worker A 正在工作中...")
        sys.stdout.flush()
        time.sleep(5)
except KeyboardInterrupt:
    print("\n🐮 Worker A: 收到關閉信號，正在離開。", flush=True)
