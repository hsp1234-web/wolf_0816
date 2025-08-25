#!/bin/bash
# 設置 -e 選項，讓腳本在任何指令返回非零退出碼時立即終止，以確保腳本的健壯性。
set -e

# --- 步驟 1: 檢查與安裝 uv ---
# 檢查 'uv' 指令是否存在於系統的 PATH 中。
# command -v 會在找到指令時返回 0，找不到時返回 1。
# &> /dev/null 用於抑制所有輸出，讓檢查過程保持靜默。
if ! command -v uv &> /dev/null
then
    # 如果 'uv' 不存在 (command -v 返回非 0)，則執行此區塊。
    echo "訊息：'uv' 指令未找到，正在透過 pip 安裝..."
    # 使用 pip 安裝 uv。--quiet 選項可以減少安裝過程中的輸出。
    pip install --quiet uv
    echo "訊息：'uv' 安裝完成。"
else
    # 如果 'uv' 已存在，則提示使用者。
    echo "訊息：'uv' 已安裝。"
fi

# --- 步驟 2: 安裝依賴並打包 ---
echo -e "\n--- 開始烘烤依賴 ---"

# 定義變數，增加可讀性與可維護性
BUILD_DIR="_build"
DEPS_DIR="${BUILD_DIR}/deps"
OUTPUT_ARCHIVE="dependencies.tar.gz"
REQUIREMENTS_FILE="requirements-unified.txt"

# 建立暫存目錄
# -p 參數可以確保如果目錄已存在，也不會報錯
echo "1/4: 正在建立暫存目錄 ${DEPS_DIR}..."
mkdir -p "${DEPS_DIR}"

# 使用 uv 將依賴安裝到目標目錄
echo "2/4: 正在使用 uv 安裝依賴從 ${REQUIREMENTS_FILE}..."
uv pip install -r "${REQUIREMENTS_FILE}" --target "${DEPS_DIR}"

# --- 關鍵修正：將原始碼與前端成品也複製到依賴目錄中 ---
echo "將原始碼 (src, services, workers) 複製到烘烤目錄..."
cp -r src "${DEPS_DIR}/"
cp -r services "${DEPS_DIR}/"
cp -r workers "${DEPS_DIR}/"
cp huey_entrypoint.py "${DEPS_DIR}/"

echo "將前端建置成品 (vue-app/dist) 複製到烘烤目錄..."
# 建立 vue-app 目錄以維持路徑結構
mkdir -p "${DEPS_DIR}/vue-app"
cp -r vue-app/dist "${DEPS_DIR}/vue-app/"
# --- 修正結束 ---

# 使用 tar 打包依賴目錄
# -C 參數會先切換到 ${DEPS_DIR} 目錄，然後才開始打包。
# '.' 表示打包該目錄下的所有內容。
# 這樣可以避免在壓縮檔中包含 '_build/deps' 這樣多餘的上層路徑。
echo "3/4: 正在將依賴打包至 ${OUTPUT_ARCHIVE}..."
tar -czf "${OUTPUT_ARCHIVE}" -C "${DEPS_DIR}" .

# 清理暫存目錄
echo "4/4: 正在清理暫存目錄 ${BUILD_DIR}..."
rm -rf "${BUILD_DIR}"

echo -e "\n✅ 成功：依賴已烘烤並打包至 ${OUTPUT_ARCHIVE}。"
