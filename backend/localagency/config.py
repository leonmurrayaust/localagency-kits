"""
localagency/config.py
══════════════════════
Configuration for LocalAgency Kits backend.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # ── General ──────────────────────────────────────────────────────────────
    app_name: str = "localagency-kits"
    version: str = "0.1.0"
    debug: bool = Field(default=False)
    environment: str = Field(default="development")  # development | staging | production

    # ── HTTP / API Gateway ───────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    dashboard_port: int = Field(default=8080)
    cors_origins: list[str] = Field(default=["*"])
    secret_key: str = Field(default="change-me-in-production")

    # ── PostgreSQL ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://localagency:localagency@localhost:5432/localagency"
    )
    database_url_sync: str = Field(
        default="postgresql://localagency:localagency@localhost:5432/localagency"
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_session_ttl: int = Field(default=86400)  # 24h
    redis_circuit_breaker_ttl: int = Field(default=300)  # 5 min
    redis_idempotency_ttl: int = Field(default=86400)  # 24h

    # ── S3 / Cold Storage ────────────────────────────────────────────────────
    s3_endpoint: Optional[str] = Field(default=None)
    s3_bucket: str = Field(default="localagency-archive")
    s3_access_key: Optional[str] = Field(default=None)
    s3_secret_key: Optional[str] = Field(default=None)
    s3_region: str = Field(default="us-east-1")

    # ── Twilio ───────────────────────────────────────────────────────────────
    twilio_account_sid: Optional[str] = Field(default=None)
    twilio_auth_token: Optional[str] = Field(default=None)
    twilio_phone_number: Optional[str] = Field(default=None)

    # ── LLM / AI Providers ───────────────────────────────────────────────────
    deepgram_api_key: Optional[str] = Field(default=None)
    elevenlabs_api_key: Optional[str] = Field(default=None)
    playht_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    default_llm_model: str = Field(default="google/gemma-2-2b-it:free")

    # ── Calendar ─────────────────────────────────────────────────────────────
    calendly_api_key: Optional[str] = Field(default=None)
    gohighlevel_api_key: Optional[str] = Field(default=None)

    # ── Billing ──────────────────────────────────────────────────────────────
    stripe_api_key: Optional[str] = Field(default=None)
    stripe_webhook_secret: Optional[str] = Field(default=None)
    stripe_price_id: str = Field(default="price_localagency_monthly")

    # ── Monitoring ───────────────────────────────────────────────────────────
    sentry_dsn: Optional[str] = Field(default=None)
    slack_webhook_url: Optional[str] = Field(default=None)
    sms_alert_number: Optional[str] = Field(default=None)

    # ── Circuit Breaker Defaults ─────────────────────────────────────────────
    cb_failure_threshold: int = Field(default=5)
    cb_window_seconds: int = Field(default=60)
    cb_cooldown_seconds: int = Field(default=30)

    # ── Rate Limits ──────────────────────────────────────────────────────────
    rate_limit_default: int = Field(default=100)  # requests per minute
    twilio_sms_rate_per_second: int = Field(default=1)
    voicekit_max_call_duration: int = Field(default=300)  # 5 min
    leadkit_max_dms_per_day: int = Field(default=20)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Get singleton settings instance."""
    return Settings()
