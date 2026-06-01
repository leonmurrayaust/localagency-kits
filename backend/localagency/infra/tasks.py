"""
localagency/infra/tasks.py
═══════════════════════════
Celery task definitions for async processing.
"""

from __future__ import annotations

from celery import Celery

from localagency.config import get_settings

settings = get_settings()

app = Celery(
    "localagency",
    broker=settings.redis_url,
    backend=settings.redis_url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# ── Schedule Configuration ──────────────────────────────────────────────────

app.conf.beat_schedule = {
    # Daily health check — 6 AM
    "daily-health-check": {
        "task": "localagency.infra.tasks.daily_health_check",
        "schedule": 86400.0,  # daily
        "args": (),
    },
    # Weekly SocialKit content batch — Sunday 8PM
    "weekly-social-batch": {
        "task": "localagency.infra.tasks.weekly_social_batch",
        "schedule": 604800.0,
        "args": (),
    },
    # Weekly GEO optimization — Wednesday 3AM
    "weekly-geo-optimization": {
        "task": "localagency.infra.tasks.weekly_geo_optimization",
        "schedule": 604800.0,
        "args": (),
    },
}

app.conf.timezone = "UTC"


# ── Task Definitions ────────────────────────────────────────────────────────

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_inbound_call(self, call_sid: str, client_id: str, from_number: str):
    """Process an inbound call via VoiceKit (async path)."""
    # TODO: Implement async call processing
    return {"status": "queued", "call_sid": call_sid}


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def send_sms_notification(self, to_number: str, message: str):
    """Send SMS notification via Twilio."""
    # TODO: Implement Twilio SMS send
    return {"status": "sent", "to": to_number}


@app.task(bind=True)
def daily_health_check(self):
    """Daily system health check — 6AM cron."""
    # TODO: Check all circuit breakers, DB connections, API credits
    return {"status": "healthy", "timestamp": ""}


@app.task(bind=True)
def weekly_social_batch(self):
    """Generate weekly social content batch — Sunday 8PM cron."""
    # TODO: Trigger HC-SK-001 for all active clients
    return {"status": "queued"}


@app.task(bind=True)
def weekly_geo_optimization(self):
    """Weekly GEO optimization — Wednesday 3AM cron."""
    # TODO: Trigger HC-GEO-001 for all active clients
    return {"status": "queued"}


@app.task(bind=True)
def send_daily_digest(self):
    """Send daily exception digest email to founder."""
    # TODO: Aggregate P0-P4 events, call volume, booking rate, costs
    return {"status": "digest_sent"}
