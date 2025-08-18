# services/static_web_server/main.py
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI(title="靜態網頁伺服器", version="0.1.0")

# 靜態檔案所在的目錄
# 我們指向 Vue 應用程式建置後的 dist 目錄
STATIC_DIR = Path(__file__).parent.parent.parent / "vue-app" / "dist"

# --- 處理單頁應用 (SPA) 的路由 ---
# 對於任何未匹配到靜態檔案的 GET 請求，都回傳 index.html
# 這確保了 Vue Router 能夠在前端處理路由
@app.get("/{full_path:path}", response_class=FileResponse)
async def serve_spa(full_path: str):
    index_path = STATIC_DIR / "index.html"
    # 基本的安全檢查，防止路徑遍歷
    if ".." in full_path:
        return FileResponse(index_path)

    # 檢查請求的路徑是否對應一個實際存在的檔案
    requested_path = STATIC_DIR / full_path
    if requested_path.is_file():
        return FileResponse(requested_path)

    # 如果不是檔案，則回傳主頁 index.html
    return FileResponse(index_path)

# --- 掛載靜態檔案目錄 ---
# 將 /assets 路徑映射到 dist/assets 目錄
# 注意：FastAPI 會先檢查掛載的路徑，然後才檢查上面的 GET 路由。
# 這就是為什麼我們需要明確地為 SPA 處理回退 (fallback)。
# 我們只掛載 assets，其他所有請求由上面的 serve_spa 處理。
app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

# --- 根路徑處理 ---
# 為了確保訪問根目錄 ("/") 時也能正確提供 index.html
@app.get("/", response_class=FileResponse)
async def read_index():
    return STATIC_DIR / "index.html"


if __name__ == "__main__":
    # 靜態伺服器運行在 8080 連接埠，這是一個常見的網頁伺服器連接埠
    uvicorn.run(app, host="0.0.0.0", port=8080)
