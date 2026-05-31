"""
localagency/models/contracts.py
═════════════════════════════════
Handoff contracts for LocalAgency Kits inter-agent communication.
Extends the AgentForge handoff contract system with 8+3 LocalAgency-specific contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DeliveryGuarantee(str, Enum):
    """Delivery guarantee levels for handoff contracts."""
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"
    BEST_EFFORT = "best_effort"


class ContractState(str, Enum):
    """Lifecycle state of a handoff contract execution."""
    PENDING = "pending"
    ROUTED = "routed"
    QC_CHECK = "qc_check"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class HandoffContract:
    """
    A single inter-agent handoff contract.

    Governs the exact data shape, delivery mode, and lifecycle expectations
    between two agents in the star-topology system.
    """
    contract_id: str
    name: str
    source: str
    target: str
    trigger: str
    description: str
    timeout_seconds: int = 60
    retry_policy: str = "3x EXPONENTIAL (5s, 15s, 45s)"
    max_retries: int = 3
    guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_LEAST_ONCE
    idempotency_key_source: str = ""
    input_schema_keys: tuple[str, ...] = ()
    output_schema_keys: tuple[str, ...] = ()


# ── All 11 LocalAgency Handoff Contracts ─────────────────────────────────────

LOCALAGENCY_CONTRACTS: list[HandoffContract] = [
    # HC-VK-001 — Inbound call or booking SMS → VoiceKit
    HandoffContract(
        contract_id="HC-VK-001",
        name="Inbound Call to VoiceKit",
        source="Ingestion",
        target="VoiceKit",
        trigger="Inbound phone call or booking SMS arriving at Twilio number",
        description="Route inbound call/booking intent to VoiceKit for AI receptionist handling. "
                    "Carries caller info, extracted intent, confidence score, and context.",
        timeout_seconds=300,
        retry_policy="3x EXPONENTIAL (5s, 15s, 45s)",
        max_retries=3,
        guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
        idempotency_key_source="call_sid",
        input_schema_keys=("caller_name", "caller_number", "intent", "confidence", "call_sid", "client_id"),
        output_schema_keys=("booking_id", "datetime", "status", "transcript_hash"),
    ),
    # HC-RK-001 — New review event → ReviewKit
    HandoffContract(
        contract_id="HC-RK-001",
        name="Review Event to ReviewKit",
        source="Ingestion",
        target="ReviewKit",
        trigger="New review posted on Google Business Profile, Yelp, or Facebook",
        description="Route a new review event to ReviewKit for auto-response. "
                    "Carries platform, rating, review text, and URL.",
        timeout_seconds=120,
        retry_policy="3x FIXED (10s)",
        max_retries=3,
        guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
        idempotency_key_source="review_id+platform",
        input_schema_keys=("platform", "rating", "text", "review_url", "author", "client_id"),
        output_schema_keys=("response_id", "response_text", "status"),
    ),
    # HC-SK-001 — Weekly cron → SocialKit
    HandoffContract(
        contract_id="HC-SK-001",
        name="Social Content Batch to SocialKit",
        source="Orchestrator",
        target="SocialKit",
        trigger="Weekly cron trigger (Sunday 8PM) to generate social content batch",
        description="Route weekly social content generation to SocialKit. "
                    "Carries client context, brand voice reference, and week schedule.",
        timeout_seconds=600,
        retry_policy="2x EXPONENTIAL (30s, 120s)",
        max_retries=2,
        guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
        idempotency_key_source="week_key+client_id",
        input_schema_keys=("client_id", "week_start", "template", "brand_voice_ref"),
        output_schema_keys=("post_ids", "status_counts"),
    ),
    # HC-LK-001 — DM opportunity → LeadKit
    HandoffContract(
        contract_id="HC-LK-001",
        name="Lead Opportunity to LeadKit",
        source="Ingestion",
        target="LeadKit",
        trigger="DM opportunity detected on Facebook/Nextdoor/Reddit",
        description="Route a recommendation request or DM opportunity to LeadKit for engagement. "
                    "Carries prospect info, match confidence, and client context.",
        timeout_seconds=120,
        retry_policy="3x FIXED (15s)",
        max_retries=3,
        guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
        idempotency_key_source="post_url+client_id",
        input_schema_keys=("source", "url", "author_name", "post_text", "match_reason", "confidence", "client_id"),
        output_schema_keys=("outreach_id", "sent_at", "status"),
    ),
    # HC-RK2-001 — New lead → ResponseKit
    HandoffContract(
        contract_id="HC-RK2-001",
        name="New Lead to ResponseKit",
        source="Ingestion",
        target="ResponseKit",
        trigger="New lead from any channel (web form, DM, SMS, voicemail callback)",
        description="Route a new lead to ResponseKit for immediate AI follow-up. "
                    "Carries lead source, contact info, message, and lead score.",
        timeout_seconds=60,
        retry_policy="3x LINEAR (5s, 10s, 15s)",
        max_retries=3,
        guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
        idempotency_key_source="SHA256(contact_info+message+timestamp)",
        input_schema_keys=("source_channel", "contact_info", "message", "lead_score", "client_id"),
        output_schema_keys=("response_id", "sent_at", "channel_used"),
    ),
    # HC-GEO-001 — Weekly GEO optimization → GEO Module
    HandoffContract(
        contract_id="HC-GEO-001",
        name="GEO Optimization Trigger",
        source="Orchestrator",
        target="GEO Module",
        trigger="Weekly GEO optimization cron (Wednesday 3AM)",
        description="Trigger weekly Google Business Profile optimization. "
                    "BEST_EFFORT — if optimization fails, next week's run handles it.",
        timeout_seconds=600,
        retry_policy="1x",
        max_retries=1,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
        idempotency_key_source="week_stamp+client_id",
        input_schema_keys=("client_id", "last_optimized", "gbp_id"),
        output_schema_keys=("actions_taken", "citation_gaps_found", "status"),
    ),
    # HC-BILL-001 — Billing event → Stripe
    HandoffContract(
        contract_id="HC-BILL-001",
        name="Billing Event to Stripe Handler",
        source="Orchestrator",
        target="Stripe",
        trigger="Billing event (subscription change, payment, dunning)",
        description="Process Stripe billing event. EXACTLY_ONCE — no double-charge tolerance. "
                    "No retry — billing events always need fresh webhook data.",
        timeout_seconds=60,
        retry_policy="0x — no retry",
        max_retries=0,
        guarantee=DeliveryGuarantee.EXACTLY_ONCE,
        idempotency_key_source="stripe_event_id",
        input_schema_keys=("client_id", "event_type", "subscription_id", "amount", "currency"),
        output_schema_keys=("invoice_id", "status", "payment_method_used"),
    ),
    # HC-EMERG-001 — Emergency escalation → Human
    HandoffContract(
        contract_id="HC-EMERG-001",
        name="Emergency to Human Escalation",
        source="Ingestion",
        target="Human Escalation",
        trigger="Emergency keyword detected or threshold breach (3+ consecutive failures)",
        description="Escalate emergency event to founder. EXACTLY_ONCE — no duplicate emergencies. "
                    "Immediate dispatch via Slack + SMS + phone (P0).",
        timeout_seconds=60,
        retry_policy="0x — no retry",
        max_retries=0,
        guarantee=DeliveryGuarantee.EXACTLY_ONCE,
        idempotency_key_source="emergency_id (UUID v7)",
        input_schema_keys=("severity", "agent", "error_detail", "call_sid", "trace_id", "client_id", "context_json"),
        output_schema_keys=("acknowledged_at", "assigned_to"),
    ),
    # HC-ESC-001 — Kit escalation → Orchestrator
    HandoffContract(
        contract_id="HC-ESC-001",
        name="Kit Escalation to Orchestrator",
        source="Any Kit",
        target="Orchestrator",
        trigger="Escalation from failed retry — all retries exhausted",
        description="Escalate a failed contract execution back to Orchestrator for reroute decision. "
                    "EXACTLY_ONCE — critical state transition.",
        timeout_seconds=30,
        retry_policy="0x — no retry",
        max_retries=0,
        guarantee=DeliveryGuarantee.EXACTLY_ONCE,
        idempotency_key_source="escalation_id (UUID v7)",
        input_schema_keys=("original_contract_id", "attempts", "error_chain_json", "agent_name", "trace_id"),
        output_schema_keys=("route_to", "retry_allowed"),
    ),
    # HC-DLQ-001 — Dead letter event → DLQ
    HandoffContract(
        contract_id="HC-DLQ-001",
        name="Dead Letter Queue Entry",
        source="Orchestrator",
        target="Dead Letter Queue",
        trigger="Contract failure after all retries exhausted — send to DLQ",
        description="Send permanently failed event to dead letter queue for founder replay. "
                    "EXACTLY_ONCE — prevent duplicate DLQ entries.",
        timeout_seconds=30,
        retry_policy="0x — no retry",
        max_retries=0,
        guarantee=DeliveryGuarantee.EXACTLY_ONCE,
        idempotency_key_source="dlq_entry_id (UUID v7)",
        input_schema_keys=("original_contract_id", "max_attempts", "last_error", "payload_snapshot_json",
                           "trace_id", "client_id"),
        output_schema_keys=("stored_at", "queue_depth"),
    ),
    # HC-SYS-001 — Circuit breaker event → Orchestrator
    HandoffContract(
        contract_id="HC-SYS-001",
        name="Circuit Breaker State Change",
        source="System Monitor",
        target="Orchestrator",
        trigger="Circuit breaker state changes (CLOSED→OPEN→HALF_OPEN→CLOSED/OPEN)",
        description="System event when a per-agent circuit breaker changes state. "
                    "EXACTLY_ONCE — critical infrastructure event.",
        timeout_seconds=30,
        retry_policy="0x — no retry",
        max_retries=0,
        guarantee=DeliveryGuarantee.EXACTLY_ONCE,
        idempotency_key_source="circuit_event_id (UUID v7)",
        input_schema_keys=("agent_name", "state_change", "failure_count", "window_seconds", "trace_id"),
        output_schema_keys=("escalated_to", "severity_assigned"),
    ),
]

# Build lookup dicts
CONTRACT_BY_ID: dict[str, HandoffContract] = {c.contract_id: c for c in LOCALAGENCY_CONTRACTS}
CONTRACT_BY_TARGET: dict[str, list[HandoffContract]] = {}
for c in LOCALAGENCY_CONTRACTS:
    CONTRACT_BY_TARGET.setdefault(c.target, []).append(c)
