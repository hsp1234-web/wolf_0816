# src/core/mini_server.py
import asyncio
import json
import logging
import sys
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

# --- Configuration ---
LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('mini_server')

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DIST_DIR = ROOT_DIR / "vue-app" / "dist"
STATUS_FILE = ROOT_DIR / "temp_status.json"

# --- WebSocket Connection Management ---
connections: list[WebSocket] = []

async def broadcast_status():
    """Reads status from file and broadcasts to all connected clients."""
    if not STATUS_FILE.is_file():
        return

    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            status_data = json.load(f)

        message = {
            "type": "INSTALL_PROGRESS",
            "payload": status_data
        }

        # Use asyncio.gather to send to all clients concurrently
        await asyncio.gather(*(ws.send_json(message) for ws in connections))
        log.info(f"Broadcasted status: {status_data['message']}")

    except (json.JSONDecodeError, IOError) as e:
        log.warning(f"Could not read or parse status file: {e}")

async def status_file_watcher():
    """Watches the status file for changes and triggers broadcast."""
    last_modified_time = -1
    while True:
        try:
            if STATUS_FILE.is_file():
                mtime = STATUS_FILE.stat().st_mtime
                if mtime > last_modified_time:
                    last_modified_time = mtime
                    await broadcast_status()
        except FileNotFoundError:
            # File might be deleted between check and stat, just ignore
            last_modified_time = -1
        except Exception as e:
            log.error(f"Error in status file watcher: {e}")

        await asyncio.sleep(0.5)

# --- WebSocket Endpoint ---
async def websocket_status_endpoint(websocket: WebSocket):
    """Handles incoming WebSocket connections for status updates."""
    await websocket.accept()
    connections.append(websocket)
    log.info(f"New client connected. Total clients: {len(connections)}")
    try:
        # Send initial status immediately on connect
        await broadcast_status()
        while True:
            # Keep the connection alive, but we don't expect messages from client
            await websocket.receive_text()
    except Exception:
        # Handles client disconnects
        pass
    finally:
        if websocket in connections:
            connections.remove(websocket)
        log.info(f"Client disconnected. Total clients: {len(connections)}")

# --- Static Files and Routing ---
# Serve the Vue app's index.html for any path not otherwise handled
async def serve_index(request):
    from starlette.responses import FileResponse
    index_path = DIST_DIR / "index.html"
    if not index_path.is_file():
        from starlette.responses import PlainTextResponse
        return PlainTextResponse("Frontend not built. Please run 'bun run build' in the vue-app directory.", status_code=503)
    return FileResponse(index_path)

routes = [
    WebSocketRoute("/ws_status", endpoint=websocket_status_endpoint),
    Mount("/assets", app=StaticFiles(directory=DIST_DIR / "assets"), name="assets"),
    Route("/{full_path:path}", endpoint=serve_index)
]

# --- Application Lifecycle ---
async def on_startup():
    log.info("🚀 Minimal server starting up...")
    # Clean up old status file if it exists
    if STATUS_FILE.exists():
        STATUS_FILE.unlink()
    # Start the background task that watches the status file
    asyncio.create_task(status_file_watcher())

async def on_shutdown():
    log.info("🌙 Minimal server shutting down...")

# --- Create App ---
app = Starlette(
    routes=routes,
    on_startup=[on_startup],
    on_shutdown=[on_shutdown]
)

# --- Main Entry Point ---
if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except (ValueError, IndexError):
            log.warning(f"Invalid port '{sys.argv[1]}'. Defaulting to {port}.")

    log.info(f"Starting minimal server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
