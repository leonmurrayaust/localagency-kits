"""
localagency/__init__.py
══════════════════════
LocalAgency Kits — VoiceKit MVP Backend.

Top-level package for the LocalAgency multi-agent SaaS platform.
VoiceKit is the first productized Kit (Phase 2, Days 31-60),
providing autonomous inbound AI call answering and appointment booking.

Architecture: Star-topology multi-agent on AgentForge orchestrator runtime.
  Client Channels → Ingestion → Orchestrator → Downstream Kit Agents
                                            ↕
                                    Dead Letter Queue / Human Escalation

Subpackages:
  - models:       Data models (client, events, contracts, routing)
  - services:     Business logic (circuit breaker, DLQ, VoiceKit state machine)
  - gateway:      FastAPI webhook receiver + internal API
  - dashboard:    Exception-only monitoring dashboard (Jinja2 + HTMX)
  - infra:        Docker, DB schema, Celery tasks, deployment config
"""

from __future__ import annotations

__version__ = "0.1.0"

# Re-export key symbols for convenience
from localagency.config import Settings, get_settings
from localagency.models import (
    BrandVoice,
    BusinessVertical,
    CallRecord,
    CallState,
    ClientProfile,
    DeliveryGuarantee,
    HandoffContract,
    IntentCategory,
    LOCALAGENCY_CONTRACTS,
    LOCALAGENCY_ROUTES,
    RouteEntry,
)
from localagency.services import (
    CircuitBreaker,
    DeadLetterEntry,
    DeadLetterQueue,
)

__all__ = [
    "__version__",
    "Settings",
    "get_settings",
    "BrandVoice",
    "BusinessVertical",
    "CallRecord",
    "CallState",
    "ClientProfile",
    "DeliveryGuarantee",
    "HandoffContract",
    "IntentCategory",
    "LOCALAGENCY_CONTRACTS",
    "LOCALAGENCY_ROUTES",
    "RouteEntry",
    "CircuitBreaker",
    "DeadLetterEntry",
    "DeadLetterQueue",
]
