# services/notification_service/main.py
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import List, Any

# --- 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"新用戶端連線: {websocket.client}. 目前連線數: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"用戶端斷線: {websocket.client}. 目前連線數: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        print(f"正在廣播訊息給 {len(self.active_connections)} 個用戶端: {message}")
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# --- Pydantic 模型 ---
class BroadcastMessage(BaseModel):
    event: str
    data: Any

# --- FastAPI 應用 ---
app = FastAPI(title="通知服務 (WebSocket)", version="0.1.0")

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Notification Service"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 我們可以讓前端發送 ping 訊息來保持連線活躍
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/broadcast", summary="向所有連線的用戶端廣播訊息")
async def broadcast_message(message: BroadcastMessage):
    """
    接收來自其他後端服務的 HTTP 請求，並將訊息透過 WebSocket 廣播出去。
    """
    try:
        await manager.broadcast(message.model_dump())
        return {"status": "success", "message": "訊息已成功廣播。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"廣播訊息時發生錯誤: {e}")


if __name__ == "__main__":
    # 通知服務運行在 8010 連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
