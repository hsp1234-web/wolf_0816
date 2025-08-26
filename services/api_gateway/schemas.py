# 繁體中文註解：
# 這個檔案定義了 API 的資料傳輸物件 (DTOs) 或稱為 Schemas。
# 使用 Pydantic 模型可以確保 API 的型別安全、提供資料驗證，並自動生成文件。

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Any, Literal

# --- 通用 Schemas ---

class Task(BaseModel):
    """代表一個獨立任務的通用模型。"""
    type: str  # 例如：'transcribe_file', 'youtube_download'
    payload: dict[str, Any]

class BatchTasksRequest(BaseModel):
    """提交批次任務的請求模型。"""
    tasks: List[Task]

class StagedFileResponse(BaseModel):
    """代表一個已暫存檔案的回應模型。"""
    file_path: str
    original_filename: str

# --- YouTube 相關 Schemas ---

class YouTubeURLRequest(BaseModel):
    """單一 YouTube URL 的請求模型。"""
    url: str
    filename: Optional[str] = None

class YouTubeProcessRequest(BaseModel):
    """處理 YouTube 影片的請求模型。"""
    requests: List[YouTubeURLRequest]
    api_key: Optional[str] = None # JULES: 新增 api_key 欄位，因為 worker 需要它
    model: Optional[str] = None
    tasks_to_run: str = "summary,transcript"
    output_format: str = "html"
    download_only: bool = False
    download_type: Literal['audio', 'video'] = 'audio'

# --- WebSocket 相關 Schemas ---

class WebSocketRequest(BaseModel):
    """WebSocket 請求的通用模型。"""
    type: str
    payload: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None # 用於點對點請求/回應

class ValidateAPIKeyRequest(BaseModel):
    """驗證 API 金鑰的請求模型。"""
    api_key: str

class ValidateAPIKeyResponse(BaseModel):
    """驗證 API 金鑰的回應模型。"""
    valid: bool
    detail: Optional[str] = None

class GeminiModel(BaseModel):
    """單一 Gemini 模型的回應模型。"""
    id: str
    name: str

class FetchGeminiModelsResponse(BaseModel):
    """獲取 Gemini 模型列表的回應模型。"""
    models: List[GeminiModel]

TaskStatus = Literal['pending', 'dispatched', 'running', 'completed', 'failed']

class TaskStatusUpdateRequest(BaseModel):
    """背景工作者用來回報任務狀態的請求模型。"""
    task_id: str
    status: TaskStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

# --- App 狀態回報 Schemas ---

class FeatureStatus(BaseModel):
    """單一功能的狀態。"""
    enabled: bool
    message: Optional[str] = None

class Features(BaseModel):
    """所有核心功能的狀態集合。"""
    transcription: FeatureStatus
    youtube_processing: FeatureStatus
    model_management: FeatureStatus

class AppStatusResponse(BaseModel):
    """`/api/v1/status` 端點的回應模型。"""
    features: Features
    app_version: str
    timestamp: datetime
