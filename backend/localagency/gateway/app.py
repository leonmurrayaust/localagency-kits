"""
localagency/gateway/app.py
═══════════════════════════
FastAPI application — API gateway for LocalAgency Kits.

Serves as the entry point for all external webhooks (Twilio, Stripe, etc.)
and provides health checking, metrics, and middleware.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from localagency.config import get_settings
from localagency.gateway.routes import health_router, webhook_router, api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup/shutdown hooks."""
    settings = get_settings()
    # TODO: Initialize DB pool, Redis client, Stripe SDK
    yield
    # TODO: Cleanup connections


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Middleware: Request ID + Trace ID ────────────────────────────────────
    @app.middleware("http")
    async def add_trace_id(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        response: Response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    # ── Middleware: Request timing ───────────────────────────────────────────
    @app.middleware("http")
    async def timing_middleware(request: Request, call_next):
        start = datetime.now(timezone.utc)
        response: Response = await call_next(request)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        response.headers["X-Response-Time-Ms"] = str(int(elapsed))
        return response

    # Register routers
    app.include_router(health_router, tags=["health"])
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(api_router, prefix="/api/v1", tags=["api"])

    return app


app = create_app()
