#!/bin/bash

# --- 環境穩定性證明腳本 ---
# 本腳本旨在證明：
# 1. 初始的安裝錯誤是由於路徑錯誤（試圖進入不存在的 'frontend' 目錄）。
# 2. 在正確的專案根目錄下，套件安裝與測試驗證流程均可正常運作。
# 這證明了開發環境本身是穩定的，不存在阻礙 Vue 開發的底層問題。

# 設定：如果任何指令失敗，腳本將立即退出
set -e

echo "---"
echo "🔵 步驟 1: 重現原始錯誤"
echo "   嘗試在子 shell 中進入一個不存在的 'frontend' 目錄..."

# 使用 '()' 來在子 shell 中執行，這樣 'cd' 的失敗不會影響主腳本的路徑
# 我們預期這個指令會失敗
if (cd frontend && pwd) 2>/dev/null; then
    echo "   ❌ 失敗：非預期地成功進入 'frontend' 目錄。腳本中止。"
    exit 1
else
    echo "   ✅ 成功：指令如預期般失敗，因為 'frontend' 目錄不存在。"
    echo "      這重現了最初導致 CWD (當前工作目錄) 錯誤的操作模式。"
fi

echo ""
echo "---"
echo "🔵 步驟 2: 證明套件安裝功能正常"
echo "   在專案根目錄執行 'bun install'..."

bun install

echo "   ✅ 成功：'bun install' 在專案根目錄下順利完成。"

echo ""
echo "---"
echo "🔵 步驟 3: 證明專案自帶的驗證流程正常"
echo "   執行 'bun run snapshot' 來進行一個完整的輕量級測試..."

bun run snapshot

echo "   ✅ 成功：'bun run snapshot' 腳本完整執行並通過驗證。"

echo ""
echo "---"
echo "✅ 結論：環境穩定性已確認"
echo "   所有測試均已通過。初始錯誤已確認為路徑問題，而非環境不穩定。"
echo "   在此環境中進行 Vue.js 開發不存在任何已知的底層阻礙。"
echo "---"
