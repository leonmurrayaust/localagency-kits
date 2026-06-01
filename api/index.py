from fastapi import FastAPI
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()

HERE = Path(__file__).parent.parent

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/{path:path}")
async def serve_static(path: str = ""):
    file_path = HERE / "index.html"
    if file_path.exists():
        return FileResponse(str(file_path))
    return {"error": "not found"}
