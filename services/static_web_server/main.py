# services/static_web_server/main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from background_tasks import install_heavy_dependencies

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在伺服器啟動時執行的程式碼
    print("INFO:     靜態網頁伺服器啟動...")
    print("INFO:     觸發背景任務：安裝重量級依賴...")
    asyncio.create_task(install_heavy_dependencies())
    yield
    # 在伺服器關閉時執行的程式碼
    print("INFO:     靜態網頁伺服器關閉。")


app = FastAPI(title="靜態網頁伺服器", version="0.2.0", lifespan=lifespan)

# 靜態檔案所在的目錄
# 我們指向 Vue 應用程式建置後的 dist 目錄
STATIC_DIR = Path(__file__).parent.parent.parent / "vue-app" / "dist"

# --- 處理單頁應用 (SPA) 的路由 ---
# 對於任何未匹配到靜態檔案的 GET 請求，都回傳 index.html
# 這確保了 Vue Router 能夠在前端處理路由
@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_spa(full_path: str):
    index_path = STATIC_DIR / "index.html"
    # 基本的安全檢查，防止路徑遍歷
    if ".." in full_path or not index_path.exists():
        # 如果 index.html 不存在，可能前端尚未建置
        return FileResponse(Path(__file__).parent / "prebuild.html")

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
if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

# --- 根路徑處理 ---
# 為了確保訪問根目錄 ("/") 時也能正確提供 index.html
@app.get("/", response_class=FileResponse, include_in_schema=False)
async def read_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return FileResponse(Path(__file__).parent / "prebuild.html")
    return FileResponse(index_path)
