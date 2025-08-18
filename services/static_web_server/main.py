import uvicorn
from fastapi import FastAPI
# from .config import settings # Commenting out as it might cause issues if not used yet

app = FastAPI(title="Static Web Server", version="0.1.0")

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Static Web Server"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)
