"""
localagency/models/events.py
══════════════════════════════
Standardized event schemas for inter-agent communication.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Intent Classifications ─────────────────────────────────────────────────

class IntentCategory(str, Enum):
    """All intents the Ingestion Agent can classify."""
    BOOKING_REQUEST = "booking_request"        # Caller wants to schedule an appointment
    REVIEW_EVENT = "review_event"              # New review posted on any platform
    SOCIAL_PUBLISH = "social_publish"          # Scheduled social content trigger
    LEAD_OPPORTUNITY = "lead_opportunity"      # DM opportunity detected on social
    RESPONSE_TRIGGER = "response_trigger"      # New lead from any channel
    GEO_OPTIMIZE = "geo_optimize"              # Weekly GEO optimization trigger
    BILLING_EVENT = "billing_event"            # Stripe subscription event
    EMERGENCY = "emergency"                    # Emergency keyword or threshold breach
    FAQ_QUERY = "faq_query"                    # Caller asking general question
    AFTER_HOURS = "after_hours"                # Call outside business hours
    LOW_CONFIDENCE = "low_confidence"          # Ingestion confidence below threshold
    UNKNOWN = "unknown"                        # Unclassifiable intent


class ChannelType(str, Enum):
    """Inbound channel types."""
    TWILIO_VOICE = "twilio_voice"
    TWILIO_SMS = "twilio_sms"
    FACEBOOK_MESSENGER = "facebook_messenger"
    INSTAGRAM_DM = "instagram_dm"
    WEBSITE_CHAT = "website_chat"
    WEB_FORM = "web_form"
    YELP = "yelp"
    GOOGLE_BUSINESS_PROFILE = "google_business_profile"
    STRIPE = "stripe"
    CALENDLY = "calendly"


# ── Ingress Event (L1 → L2) ─────────────────────────────────────────────

class IngressEvent(BaseModel):
    """
    Normalized inbound event from any channel adapter.
    This is the standard envelope that all adapters produce.
    """
    event_id: str = Field(description="UUID v7")
    channel: ChannelType
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    client_id: Optional[str] = Field(default=None)
    trace_id: str = Field(default="")

    model_config = {"extra": "allow"}


# ── Classified Event (L2 → L3) ─────────────────────────────────────────

class ClassifiedEvent(BaseModel):
    """
    Output from the Ingestion Agent after LLM intent classification.
    """
    event_id: str = Field(description="Same as IngressEvent.event_id — trace continuity")
    intent: IntentCategory
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="LLM confidence score")
    entities: dict[str, Any] = Field(default_factory=dict, description="Extracted entities")
    caller_name: Optional[str] = Field(default=None)
    caller_number: Optional[str] = Field(default=None)
    client_id: Optional[str] = Field(default=None)
    trace_id: str = Field(default="")
    original_channel: ChannelType
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# ── Handoff Envelope (L3 → L4) ──────────────────────────────────────────

class HandoffEnvelope(BaseModel):
    """
    Envelope wrapping a handoff from Orchestrator to a Kit Agent.
    Carries contract reference, idempotency key, trace context.
    """
    envelope_id: str = Field(description="UUID v7")
    contract_id: str = Field(description="e.g. 'HC-VK-001'")
    source_agent: str
    target_agent: str
    payload: dict[str, Any]
    idempotency_key: str = Field(description="Unique key for dedup")
    trace_id: str = Field(default="")
    timeout_seconds: int = Field(default=60)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = {"extra": "forbid"}


# ── Output Event (L4 → L5) ─────────────────────────────────────────────

class OutputEvent(BaseModel):
    """
    Result from a Kit Agent after processing a handoff.
    Flows to Response Channel Manager for delivery.
    """
    event_id: str
    contract_id: str
    envelope_id: str
    status: str = Field(description="completed | failed | escalated")
    result: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = Field(default=None)
    trace_id: str = Field(default="")
    processing_time_ms: int = Field(default=0)

    model_config = {"extra": "forbid"}


# ── Emergency / Escalation Events ──────────────────────────────────────

class EmergencyEvent(BaseModel):
    """Emergency escalation from any Kit to founder."""
    emergency_id: str = Field(description="UUID v7")
    severity: str = Field(description="P0 | P1 | P2 | P3 | P4")
    agent: str = Field(description="Which agent escalated")
    error_detail: str = Field(default="")
    call_sid: Optional[str] = Field(default=None)
    client_id: Optional[str] = Field(default=None)
    context: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default="")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DeadLetterEvent(BaseModel):
    """Event that exhausted all retries and is sent to DLQ."""
    dlq_entry_id: str = Field(description="UUID v7")
    original_contract_id: str
    max_attempts: int
    last_error: str
    payload_snapshot: dict[str, Any] = Field(default_factory=dict)
    error_chain: list[str] = Field(default_factory=list)
    trace_id: str = Field(default="")
    client_id: Optional[str] = Field(default=None)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    replayed: bool = Field(default=False)
    replay_count: int = Field(default=0)


# ── Call Events (VoiceKit-specific) ────────────────────────────────────

class CallState(str, Enum):
    """States in the VoiceKit LangGraph state machine."""
    INBOUND_CALL = "inbound_call"
    IVR_GREETING = "ivr_greeting"
    LLM_INTENT_CLASSIFY = "llm_intent_classify"
    BOOKING_INTENT = "booking_intent"
    CALENDAR_CHECK = "calendar_check"
    SLOT_OFFER = "slot_offer"
    CONFIRM_BOOKING = "confirm_booking"
    SMS_CONFIRM = "sms_confirm"
    AFTER_HOURS = "after_hours"
    VOICEMAIL_CAPTURE = "voicemail_capture"
    TRANSCRIBE = "transcribe"
    SMS_OWNER = "sms_owner"
    EMERGENCY = "emergency"
    ESCALATE_HUMAN = "escalate_human"
    ALERT_FOUNDER = "alert_founder"
    FAQ_QUERY = "faq_query"
    ANSWER_FROM_KB = "answer_from_kb"
    OFFER_BOOKING = "offer_booking"
    LOW_CONFIDENCE = "low_confidence"
    TRANSFER_HUMAN = "transfer_human"
    LOG = "log"
    DROPPED_MID_FLOW = "dropped_mid_flow"
    SMS_RESUME_LINK = "sms_resume_link"
    END = "end"


class CallRecord(BaseModel):
    """Persistent record of a single inbound call."""
    call_sid: str
    client_id: str
    from_number: str
    to_number: str
    state: CallState = CallState.INBOUND_CALL
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: Optional[str] = Field(default=None)
    duration_seconds: Optional[int] = Field(default=None)
    transcript: Optional[str] = Field(default=None)
    intent: Optional[IntentCategory] = Field(default=None)
    booking_made: bool = Field(default=False)
    booking_ref: Optional[str] = Field(default=None)
    escalated: bool = Field(default=False)
    error: Optional[str] = Field(default=None)
    trace_id: str = Field(default="")
    api_cost: float = Field(default=0.0)
