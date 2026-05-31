"""
localagency/models/routing.py
═══════════════════════════════
Deterministic routing table for LocalAgency Kits.
No AI at routing time — pure lookup-based intent→target mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from localagency.models.events import IntentCategory


class RoutePriority(int, Enum):
    """Priority for route dispatch. Lower number = higher priority."""
    IMMEDIATE = 10
    HIGH = 20
    NORMAL = 30
    LOW = 40
    DEFERRED = 50


@dataclass(frozen=True)
class RouteEntry:
    """
    A single deterministic route entry.
    Maps an intent (from Ingestion Agent classification) to a target Kit agent
    via a specific handoff contract.

    DESIGN RULE: No AI at routing time. All fields are concrete values.
    """
    route_id: str
    intent: IntentCategory
    target_agent: str
    contract_id: str
    description: str
    min_confidence: float = 0.70
    priority: RoutePriority = RoutePriority.NORMAL
    timeout_seconds: int = 60
    allow_retry: bool = True
    tags: tuple[str, ...] = ()


# ── LocalAgency Routing Table ─────────────────────────────────────────────────

LOCALAGENCY_ROUTES: list[RouteEntry] = [
    RouteEntry(
        route_id="R-LA-001",
        intent=IntentCategory.BOOKING_REQUEST,
        target_agent="VoiceKit",
        contract_id="HC-VK-001",
        description="Inbound call with booking intent → VoiceKit LangGraph state machine",
        min_confidence=0.70,
        priority=RoutePriority.IMMEDIATE,
        timeout_seconds=300,
        tags=("voicekit", "booking", "call"),
    ),
    RouteEntry(
        route_id="R-LA-002",
        intent=IntentCategory.REVIEW_EVENT,
        target_agent="ReviewKit",
        contract_id="HC-RK-001",
        description="New review event → ReviewKit for auto-response",
        min_confidence=0.80,
        priority=RoutePriority.HIGH,
        timeout_seconds=120,
        tags=("reviewkit", "reputation"),
    ),
    RouteEntry(
        route_id="R-LA-003",
        intent=IntentCategory.SOCIAL_PUBLISH,
        target_agent="SocialKit",
        contract_id="HC-SK-001",
        description="Weekly social content generation batch → SocialKit",
        min_confidence=0.90,
        priority=RoutePriority.LOW,
        timeout_seconds=600,
        allow_retry=False,
        tags=("socialkit", "content", "weekly"),
    ),
    RouteEntry(
        route_id="R-LA-004",
        intent=IntentCategory.LEAD_OPPORTUNITY,
        target_agent="LeadKit",
        contract_id="HC-LK-001",
        description="DM opportunity detected → LeadKit for outreach",
        min_confidence=0.75,
        priority=RoutePriority.NORMAL,
        timeout_seconds=120,
        tags=("leadkit", "outreach", "dm"),
    ),
    RouteEntry(
        route_id="R-LA-005",
        intent=IntentCategory.RESPONSE_TRIGGER,
        target_agent="ResponseKit",
        contract_id="HC-RK2-001",
        description="New lead from any channel → ResponseKit for immediate follow-up",
        min_confidence=0.70,
        priority=RoutePriority.IMMEDIATE,
        timeout_seconds=60,
        tags=("responsekit", "lead", "speed-to-lead"),
    ),
    RouteEntry(
        route_id="R-LA-006",
        intent=IntentCategory.GEO_OPTIMIZE,
        target_agent="GEO Module",
        contract_id="HC-GEO-001",
        description="Weekly GEO optimization trigger → GEO Module",
        min_confidence=0.90,
        priority=RoutePriority.DEFERRED,
        timeout_seconds=600,
        allow_retry=False,
        tags=("geo", "optimization", "weekly"),
    ),
    RouteEntry(
        route_id="R-LA-007",
        intent=IntentCategory.BILLING_EVENT,
        target_agent="Stripe",
        contract_id="HC-BILL-001",
        description="Stripe billing event → Billing handler",
        min_confidence=0.95,
        priority=RoutePriority.IMMEDIATE,
        timeout_seconds=60,
        allow_retry=False,
        tags=("billing", "stripe", "subscription"),
    ),
    RouteEntry(
        route_id="R-LA-008",
        intent=IntentCategory.EMERGENCY,
        target_agent="Human Escalation",
        contract_id="HC-EMERG-001",
        description="Emergency keyword or threshold breach → founder immediate alert",
        min_confidence=0.85,
        priority=RoutePriority.IMMEDIATE,
        timeout_seconds=60,
        allow_retry=False,
        tags=("emergency", "p0", "escalation"),
    ),
    RouteEntry(
        route_id="R-LA-009",
        intent=IntentCategory.FAQ_QUERY,
        target_agent="VoiceKit",
        contract_id="HC-VK-001",
        description="General FAQ query → VoiceKit knowledge base answer → offer booking",
        min_confidence=0.70,
        priority=RoutePriority.NORMAL,
        timeout_seconds=120,
        tags=("voicekit", "faq"),
    ),
    RouteEntry(
        route_id="R-LA-010",
        intent=IntentCategory.AFTER_HOURS,
        target_agent="VoiceKit",
        contract_id="HC-VK-001",
        description="After-hours call → voicemail capture + SMS owner",
        min_confidence=0.80,
        priority=RoutePriority.HIGH,
        timeout_seconds=120,
        tags=("voicekit", "after-hours", "voicemail"),
    ),
    RouteEntry(
        route_id="R-LA-011",
        intent=IntentCategory.LOW_CONFIDENCE,
        target_agent="Human Escalation",
        contract_id="HC-EMERG-001",
        description="Low-confidence classification → transfer to founder or voicemail",
        min_confidence=0.0,
        priority=RoutePriority.HIGH,
        timeout_seconds=120,
        allow_retry=False,
        tags=("low-confidence", "fallback", "escalation"),
    ),
]

# Build lookup dicts
ROUTE_BY_ID: dict[str, RouteEntry] = {r.route_id: r for r in LOCALAGENCY_ROUTES}
ROUTE_BY_INTENT: dict[IntentCategory, RouteEntry] = {r.intent: r for r in LOCALAGENCY_ROUTES}
