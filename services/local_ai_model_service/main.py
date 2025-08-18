# services/local_ai_model_service/main.py
# 這是 AI 本地模型服務的進入點

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from faster_whisper import WhisperModel
import os

# --- Pydantic 模型定義 ---
class TranscriptionRequest(BaseModel):
    """
    定義轉錄請求的資料結構。
    """
    # 要轉錄的音訊檔案的絕對路徑。
    # 重要提示：在真實系統中，此路徑必須經過驗證且來自可信來源，
    # 以防止路徑遍歷等安全漏洞。我們假設此服務僅由其他
    # 提供安全路徑的可信後端服務呼叫。
    file_path: str

# --- FastAPI 應用設定 ---
app = FastAPI(title="AI 本地模型服務", version="0.1.0")

# --- 模型載入 ---
# 在應用啟動時載入模型。這是一個耗時的操作。
# 我們將模型儲存在 app.state 中，以便在端點中存取。
@app.on_event("startup")
def load_model():
    """
    應用啟動時將 Whisper 模型載入記憶體。
    這使得轉錄請求能被更快地處理。
    """
    model_size = "base" # 使用較小的模型以加快載入速度並減少資源使用。
    print(f"正在載入 Whisper 模型 '{model_size}'...")
    try:
        # 在沒有 GPU 的伺服器上，使用 CPU 和 int8 量化以獲得更好效能。
        app.state.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("Whisper 模型載入成功！")
    except Exception as e:
        print(f"錯誤：無法載入 Whisper 模型。 {e}")
        app.state.model = None

# --- API 端點 ---
@app.get("/", summary="服務健康檢查")
def read_root():
    """
    健康檢查端點，同時回報模型是否已載入。
    """
    model_status = "loaded" if app.state.model else "not loaded"
    return {"status": "ok", "service": "AI Local Model Service", "model_status": model_status}

@app.post("/transcribe", summary="轉錄音訊檔案")
async def transcribe_audio(request: TranscriptionRequest):
    """
    接收音訊檔案的路徑並回傳轉錄結果。
    """
    if not app.state.model:
        raise HTTPException(status_code=503, detail="模型目前無法使用，請稍後再試。")

    file_path = request.file_path
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail=f"提供的檔案路徑不存在或不是一個檔案: {file_path}")

    try:
        print(f"開始轉錄檔案: {file_path}")
        segments, info = app.state.model.transcribe(file_path, beam_size=5)

        print(f"偵測到的語言: {info.language} (機率: {info.language_probability:.2f})")

        # 將所有片段的文字組合起來
        full_text = "".join(segment.text for segment in segments)

        print("轉錄完成。")
        return {
            "file_path": file_path,
            "language": info.language,
            "language_probability": info.language_probability,
            "transcription": full_text.strip()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"轉錄過程中發生錯誤: {e}")

if __name__ == "__main__":
    # 使用 uvicorn 來啟動服務，監聽在 8002 連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
