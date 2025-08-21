# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyfiglet==1.0.2"
# ]
# ///

import time
import sys
from pyfiglet import figlet_format

print("🎨 Worker B: 啟動中...", flush=True)

try:
    count = 0
    while True:
        output = figlet_format(f"Worker B loop {count}", font="slant")
        print(output, flush=True)
        count += 1
        time.sleep(7)
except KeyboardInterrupt:
    print("\n🎨 Worker B: 收到關閉信號，正在離開。", flush=True)
