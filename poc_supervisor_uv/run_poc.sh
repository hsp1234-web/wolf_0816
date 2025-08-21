#!/bin/bash

echo "--- POC 啟動腳本 (v3 - 除錯模式) ---"

# 步驟 1: 安裝必要的工具
echo "步驟 1: 正在安裝 uv 和 supervisor..."
pip install uv==0.1.11 supervisor==4.2.5
if [ $? -ne 0 ]; then
    echo "錯誤：安裝 uv 或 supervisor 失敗。"
    exit 1
fi
echo "✅ 工具安裝完成。"

# 步驟 2: 直接在前景啟動 Supervisor
echo "步驟 2: 正在前景啟動 supervisord 以進行除錯..."
echo "所有輸出將直接顯示在下方。按 Ctrl+C 來停止。"

# 我們直接執行 supervisord，不使用 trap 或背景處理，以查看原始輸出
supervisord -c poc_supervisor_uv/supervisord.conf
