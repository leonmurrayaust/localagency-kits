"""
localagency/gateway/routes.py
══════════════════════════════
Route definitions for the FastAPI gateway.

Separated into:
  - health_router:  Health checks, readiness probes
  - webhook_router: Inbound webhooks from Twilio, Stripe, etc.
  - api_router:     Internal REST API endpoints
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from localagency.config import get_settings
from localagency.models.events import ChannelType, IngressEvent, IntentCategory
from localagency.models.routing import ROUTE_BY_INTENT

# ── Routers ──────────────────────────────────────────────────────────────────

health_router = APIRouter()
webhook_router = APIRouter()
api_router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@health_router.get("/health")
async def health_check():
    """Basic health check — always returns 200 if the app is running."""
    return {
        "status": "ok",
        "version": get_settings().version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@health_router.get("/readiness")
async def readiness_probe():
    """
    Readiness probe — checks that downstream dependencies are available.
    Returns 200 when all systems are go, 503 if degraded.
    """
    # TODO: Actually check Redis, PostgreSQL, Twilio connectivity
    return {
        "status": "ready",
        "checks": {
            "redis": "ok",
            "postgresql": "ok",
            "twilio": "ok",
        },
    }


@health_router.get("/health/components")
async def component_health():
    """Per-component health status for the exception dashboard."""
    # TODO: Real per-component checks from circuit breaker store
    return {
        "api_gateway": "healthy",
        "orchestrator": "healthy",
        "voicekit": "healthy",
        "redis": "connected",
        "postgresql": "connected",
        "twilio": "connected",
        "last_webhook_receipt": None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@webhook_router.post("/twilio/voice")
async def twilio_voice_webhook(request: Request):
    """
    Receive inbound Twilio Voice call webhook.
    Returns TwiML for the initial greeting.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    from_number = form_data.get("From", "")
    to_number = form_data.get("To", "")

    # Create normalized ingress event
    event = IngressEvent(
        event_id=str(uuid.uuid4()),
        channel=ChannelType.TWILIO_VOICE,
        raw_payload=dict(form_data),
        trace_id=request.state.trace_id,
    )

    # TODO: L1 → L2 → L3 → L4 pipeline
    # For now, return a basic TwiML greeting response
    twiml_response = '<?xml version="1.0" encoding="UTF-8"?>'
    twiml_response += "<Response><Say>Thank you for calling. One moment please.</Say></Response>"

    return Response(
        content=twiml_response,
        media_type="application/xml",
    )


@webhook_router.post("/twilio/sms")
async def twilio_sms_webhook(request: Request):
    """Receive inbound Twilio SMS webhook."""
    form_data = await request.form()
    # TODO: Route to ResponseKit via HC-RK2-001
    return {"status": "received", "message_sid": form_data.get("MessageSid", "")}


@webhook_router.post("/twilio/status")
async def twilio_status_webhook(request: Request):
    """Receive Twilio call status callback."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    # TODO: Update CallRecord in DB
    return {"status": "logged"}


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    """Receive Stripe webhook events (subscriptions, payments)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    # TODO: Verify Stripe signature and route via HC-BILL-001
    return {"status": "received"}


@webhook_router.post("/calendly")
async def calendly_webhook(request: Request):
    """Receive Calendly booking events."""
    body = await request.json()
    # TODO: Update booking state, trigger ReviewKit review request later
    return {"status": "received"}


@webhook_router.post("/leads")
async def lead_capture_webhook(request: Request):
    """Receive lead events from web forms, chat widgets, etc."""
    body = await request.json()
    # TODO: Route to ResponseKit via HC-RK2-001
    return {"status": "received"}


@webhook_router.post("/gbp")
async def gbp_webhook(request: Request):
    """Receive Google Business Profile notifications (Phase 3)."""
    body = await request.json()
    # TODO: Route to ReviewKit via HC-RK-001
    return {"status": "received"}


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@api_router.get("/clients")
async def list_clients():
    """List all active client profiles."""
    # TODO: Read from PostgreSQL
    return {"clients": []}


@api_router.get("/clients/{client_id}")
async def get_client(client_id: str):
    """Get a single client profile by ID."""
    # TODO: Read from PostgreSQL
    return {"client_id": client_id, "business_name": "", "status": "not_implemented"}


@api_router.get("/clients/{client_id}/stats")
async def get_client_stats(client_id: str):
    """Get per-client KPIs: call volume, booking rate, etc."""
    # TODO: Aggregate from events
    return {
        "client_id": client_id,
        "calls_total": 0,
        "bookings_made": 0,
        "booking_rate": 0.0,
        "api_cost_estimate": 0.0,
    }


@api_router.get("/calls")
async def list_calls(client_id: Optional[str] = None, limit: int = 50):
    """List recent call records, optionally filtered by client."""
    return {"calls": [], "total": 0, "limit": limit}


@api_router.get("/circuit-breakers")
async def list_circuit_breakers():
    """List all circuit breaker states."""
    return {"breakers": []}


# ═══════════════════════════════════════════════════════════════════════════════
# KIT API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@api_router.post("/kits/reviews/generate-response")
async def kit_review_response(body: dict):
    from localagency.services.reviewkit import generate_review_response
    text = await generate_review_response(
        review_text=body.get("review_text", ""),
        rating=body.get("rating", 5),
        business_name=body.get("business_name", ""),
        reviewer_name=body.get("reviewer_name", ""),
    )
    return {"response": text}


@api_router.post("/kits/reviews/generate-request")
async def kit_review_request(body: dict):
    from localagency.services.reviewkit import generate_review_request_sms
    text = await generate_review_request_sms(
        business_name=body.get("business_name", ""),
        service_provided=body.get("service_provided", ""),
    )
    return {"sms": text}


@api_router.post("/kits/social/generate-post")
async def kit_social_post(body: dict):
    from localagency.services.socialkit import generate_social_post
    text = await generate_social_post(
        business_name=body.get("business_name", ""),
        vertical=body.get("vertical", ""),
        topic=body.get("topic", ""),
        season=body.get("season", ""),
        style=body.get("style", "educational"),
    )
    return {"post": text}


@api_router.post("/kits/social/generate-batch")
async def kit_social_batch(body: dict):
    from localagency.services.socialkit import generate_post_batch
    posts = await generate_post_batch(
        business_name=body.get("business_name", ""),
        vertical=body.get("vertical", ""),
        count=body.get("count", 4),
        season=body.get("season", ""),
    )
    return {"posts": posts}


@api_router.post("/kits/leads/generate-dm")
async def kit_lead_dm(body: dict):
    from localagency.services.leadkit import generate_dm
    text = await generate_dm(
        business_name=body.get("business_name", ""),
        vertical=body.get("vertical", ""),
        prospect_name=body.get("prospect_name", ""),
        request_context=body.get("request_context", ""),
    )
    return {"dm": text}


@api_router.post("/kits/leads/score")
async def kit_lead_score(body: dict):
    from localagency.services.leadkit import score_lead
    result = await score_lead(
        lead_text=body.get("lead_text", ""),
        vertical=body.get("vertical", ""),
    )
    return result


@api_router.post("/kits/response/generate")
async def kit_response_generate(body: dict):
    from localagency.services.responsekit import generate_lead_response
    text = await generate_lead_response(
        inquiry=body.get("inquiry", ""),
        business_name=body.get("business_name", ""),
        vertical=body.get("vertical", ""),
        source=body.get("source", ""),
        customer_name=body.get("customer_name", ""),
    )
    return {"response": text}


@api_router.post("/kits/response/follow-up")
async def kit_response_follow_up(body: dict):
    from localagency.services.responsekit import generate_follow_up
    text = await generate_follow_up(
        previous_exchange=body.get("previous_exchange", ""),
        days_since=body.get("days_since", 3),
        business_name=body.get("business_name", ""),
    )
    return {"follow_up": text}


# ═══════════════════════════════════════════════════════════════════════════════
# STRIPE WEBHOOK
# ═══════════════════════════════════════════════════════════════════════════════

@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    import stripe
    from localagency.config import get_settings
    settings = get_settings()
    stripe.api_key = settings.stripe_api_key

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email", "")
        # TODO: provision new client in PostgreSQL
        return {"status": "provisioned", "email": customer_email}

    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        status = subscription.get("status", "")
        # TODO: update client subscription status in PostgreSQL
        return {"status": "updated", "subscription_status": status}

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        # TODO: deactivate client in PostgreSQL
        return {"status": "canceled"}

    return {"status": "received"}
