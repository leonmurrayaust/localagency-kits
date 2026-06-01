import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request
from fastapi.responses import Response
from localagency.gateway.app import app as fastapi_app

app = FastAPI()

# Vercel strips the /api prefix from serverless function paths,
# but ASGI apps may receive the full path including /api.
# This middleware ensures correct path routing.
@app.middleware("http")
async def strip_api_prefix(request: Request, call_next):
    path = request.scope.get("path", "")
    if path.startswith("/api"):
        request.scope["path"] = path[4:] or "/"
        request.scope["root_path"] = "/api"
    return await call_next(request)

app.mount("/", fastapi_app)

handler = app
