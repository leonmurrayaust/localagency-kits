"""
localagency/dashboard/app.py
══════════════════════════════
Exception-only monitoring dashboard for the founder.

Built with FastAPI + Jinja2 + HTMX.
5 views + 3 HTMX fragments with auto-refresh.

Design principle: exception-only. The founder sees only P0/P1 events
(Slack+SMS, <5 min response) and a daily email digest. The dashboard
exists for on-demand deep dives, not real-time monitoring.

State management:
  - DashboardDataService is the single source of truth for all views.
  - Circuit breaker states, DLQ entries, call records all flow through it.
  - Phase 1 uses Memory stores; Phase 2 swaps to Redis/PostgreSQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from localagency.config import get_settings
from localagency.dashboard.services import DashboardDataService
from localagency.models.events import CallRecord, CallState, EmergencyEvent

HERE = Path(__file__).parent
TEMPLATES_DIR = HERE / "templates"
STATIC_DIR = HERE / "static"
FRAGMENTS_DIR = TEMPLATES_DIR / "fragments"

# Ensure directories exist
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
FRAGMENTS_DIR.mkdir(parents=True, exist_ok=True)

dashboard_app = FastAPI(title="LocalAgency Kits — Exception Dashboard")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── Global singleton data service ──────────────────────────────────────────────
# Phase 1: Memory stores. Phase 2: Swap to RedisCircuitBreakerStore + PostgreSQL.
_data_service: Optional[DashboardDataService] = None


def get_data_service() -> DashboardDataService:
    """Get or create the dashboard data service singleton."""
    global _data_service
    if _data_service is None:
        _data_service = DashboardDataService()
        # Register default circuit breakers for monitoring
        for agent in ("voicekit", "orchestrator", "twilio-webhook", "llm-api", "stripe"):
            _data_service.register_circuit_breaker(agent)
    return _data_service


# ── Serve static files ────────────────────────────────────────────────────────

dashboard_app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


# ═══════════════════════════════════════════════════════════════════════════════
# VIEWS
# ═══════════════════════════════════════════════════════════════════════════════


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Main dashboard — summary cards + recent calls + system health."""
    svc = get_data_service()
    stats = await svc.get_overview_stats()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            **stats,
        },
    )


@dashboard_app.get("/alerts", response_class=HTMLResponse)
async def alerts_view(
    request: Request,
    severity: Optional[str] = Query(None, description="Filter by severity (P0, P1, P2, P3, P4)"),
    limit: int = Query(50, ge=1, le=200),
):
    """P0/P1 alerts view with optional severity filter."""
    svc = get_data_service()
    alerts = await svc.get_alerts(severity=severity, limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="alerts.html",
        context={
            "request": request,
            "alerts": alerts,
            "active_severity": severity or "all",
            "alert_count": len(alerts),
        },
    )


@dashboard_app.get("/missed-calls", response_class=HTMLResponse)
async def missed_calls_view(
    request: Request,
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    limit: int = Query(50, ge=1, le=200),
):
    """Missed calls view — calls not handled by VoiceKit."""
    svc = get_data_service()
    missed = await svc.get_missed_calls(client_id=client_id, limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="missed_calls.html",
        context={
            "request": request,
            "missed_calls": missed,
            "active_client": client_id or "all",
            "missed_count": len(missed),
        },
    )


@dashboard_app.get("/bookings", response_class=HTMLResponse)
async def bookings_view(
    request: Request,
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    limit: int = Query(50, ge=1, le=200),
):
    """Booking confirmations view."""
    svc = get_data_service()
    bookings = await svc.get_bookings(client_id=client_id, limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="bookings.html",
        context={
            "request": request,
            "bookings": bookings,
            "active_client": client_id or "all",
            "booking_count": len(bookings),
        },
    )


@dashboard_app.get("/errors", response_class=HTMLResponse)
async def error_log_view(
    request: Request,
    severity: Optional[str] = Query(None, description="Filter by severity (P0-P4)"),
    limit: int = Query(100, ge=1, le=500),
):
    """System error log view with DLQ entries surfaced."""
    svc = get_data_service()
    errors = await svc.get_errors(severity=severity, limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="error_log.html",
        context={
            "request": request,
            "errors": errors,
            "active_severity": severity or "all",
            "error_count": len(errors),
        },
    )


@dashboard_app.get("/circuit-breakers", response_class=HTMLResponse)
async def circuit_breakers_view(request: Request):
    """Circuit breaker states view."""
    svc = get_data_service()
    breakers = await svc.get_circuit_breakers()
    health = await svc.get_health_status()

    return templates.TemplateResponse(
        request=request,
        name="circuit_breakers.html",
        context={
            "request": request,
            "breakers": breakers,
            "health": health,
            "breaker_count": len(breakers),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HTMX FRAGMENTS (auto-refresh)
# ═══════════════════════════════════════════════════════════════════════════════


@dashboard_app.get("/fragments/alert-count", response_class=HTMLResponse)
async def alert_count_fragment():
    """Auto-refreshing alert count badge (30s)."""
    svc = get_data_service()
    count = await svc.get_alert_count()
    color = "bg-red-500" if count > 0 else "bg-gray-600"
    return HTMLResponse(
        f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {color} text-white">{count}</span>'
    )


@dashboard_app.get("/fragments/recent-calls", response_class=HTMLResponse)
async def recent_calls_fragment():
    """Auto-refreshing recent calls table fragment (15s)."""
    svc = get_data_service()
    calls = svc._get_recent_calls(5)

    if not calls:
        return HTMLResponse('<tbody><tr><td colspan="4" class="text-gray-500 text-center py-4">No recent calls</td></tr></tbody>')

    rows = ""
    for call in calls:
        ts = (call.get("timestamp") or "").replace("T", " ")[:19]
        cid = (call.get("client_id") or "")[:12]
        dur = call.get("duration", 0)
        outcome = ""
        if call.get("booking_made"):
            outcome = '<span class="text-green-400 font-medium">Booked</span>'
        elif call.get("escalated"):
            outcome = '<span class="text-red-400 font-medium">Escalated</span>'
        elif call.get("error"):
            outcome = '<span class="text-yellow-400 font-medium">Error</span>'
        else:
            outcome = '<span class="text-gray-400">Completed</span>'
        rows += f'<tr class="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">'
        rows += f'<td class="py-2 text-gray-300">{ts}</td>'
        rows += f'<td class="py-2"><span class="text-gray-300">{cid}</span></td>'
        rows += f'<td class="py-2">{outcome}</td>'
        rows += f'<td class="py-2 text-right text-gray-500">{dur}s</td>'
        rows += "</tr>"

    return HTMLResponse(f"<tbody>{rows}</tbody>")


@dashboard_app.get("/fragments/health-status", response_class=HTMLResponse)
async def health_status_fragment():
    """Auto-refreshing health status fragment (30s)."""
    svc = get_data_service()
    health = await svc.get_health_status()

    if health.get("overall") == "healthy":
        msg = '<div class="text-green-400 font-medium flex items-center"><span class="w-2 h-2 bg-green-400 rounded-full mr-2"></span>All systems operational</div>'
    else:
        msg = f'<div class="text-red-400 font-medium flex items-center"><span class="w-2 h-2 bg-red-400 rounded-full mr-2 animate-pulse"></span>{health.get("message", "Degraded")}</div>'

    return HTMLResponse(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL API ENDPOINTS (JSON for programmatic access)
# ═══════════════════════════════════════════════════════════════════════════════


@dashboard_app.get("/api/stats")
async def api_overview_stats():
    """JSON endpoint for external monitoring / aggregators."""
    svc = get_data_service()
    stats = await svc.get_overview_stats()
    return JSONResponse(stats)


@dashboard_app.get("/api/health")
async def api_health():
    """JSON health check — same data as /fragments/health-status but as JSON."""
    svc = get_data_service()
    health = await svc.get_health_status()
    return JSONResponse(health)


@dashboard_app.get("/api/circuit-breakers")
async def api_circuit_breakers():
    """JSON circuit breaker states."""
    svc = get_data_service()
    breakers = await svc.get_circuit_breakers()
    return JSONResponse(breakers)


@dashboard_app.get("/api/alerts")
async def api_alerts(severity: Optional[str] = None, limit: int = 50):
    """JSON alerts endpoint."""
    svc = get_data_service()
    alerts = await svc.get_alerts(severity=severity, limit=limit)
    return JSONResponse(alerts)


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DATA FOR DEMO / DEVELOPMENT
# ═══════════════════════════════════════════════════════════════════════════════


@dashboard_app.get("/_seed")
async def seed_demo_data():
    """Seed demo data for development — populates the dashboard with sample records."""
    svc = get_data_service()
    import uuid
    from datetime import datetime, timezone

    # Seed call records
    demo_calls = [
        CallRecord(
            call_sid="CA-demo-001",
            client_id="client-001",
            from_number="+16025551234",
            to_number="+16025550001",
            state=CallState.END,
            started_at="2026-05-31T09:15:00+00:00",
            ended_at="2026-05-31T09:18:30+00:00",
            duration_seconds=210,
            intent="booking_request",
            booking_made=True,
            booking_ref="BK-001A",
            trace_id="trace-001",
        ),
        CallRecord(
            call_sid="CA-demo-002",
            client_id="client-002",
            from_number="+16025555678",
            to_number="+16025550002",
            state=CallState.END,
            started_at="2026-05-31T10:00:00+00:00",
            ended_at="2026-05-31T10:02:15+00:00",
            duration_seconds=135,
            escalated=True,
            error="Low confidence classification — transferred to human",
            trace_id="trace-002",
        ),
        CallRecord(
            call_sid="CA-demo-003",
            client_id="client-001",
            from_number="+16025559012",
            to_number="+16025550001",
            state=CallState.END,
            started_at="2026-05-31T11:30:00+00:00",
            ended_at="2026-05-31T11:35:00+00:00",
            duration_seconds=300,
            intent="faq_query",
            booking_made=False,
            trace_id="trace-003",
        ),
        CallRecord(
            call_sid="CA-demo-004",
            client_id="client-003",
            from_number="+16025553456",
            to_number="+16025550003",
            state=CallState.END,
            started_at="2026-05-31T14:00:00+00:00",
            ended_at="2026-05-31T14:05:30+00:00",
            duration_seconds=330,
            intent="booking_request",
            booking_made=True,
            booking_ref="BK-004B",
            trace_id="trace-004",
        ),
        CallRecord(
            call_sid="CA-demo-005",
            client_id="client-002",
            from_number="+16025557890",
            to_number="+16025550002",
            state=CallState.END,
            started_at="2026-05-31T15:45:00+00:00",
            ended_at="2026-05-31T15:46:30+00:00",
            duration_seconds=90,
            escalated=True,
            error="Circuit breaker OPEN — VoiceKit unavailable. Fallback to voicemail.",
            trace_id="trace-005",
        ),
    ]
    for call in demo_calls:
        svc.store_call(call)

    # Seed alerts
    demo_alerts = [
        EmergencyEvent(
            emergency_id=str(uuid.uuid4()),
            severity="P1",
            agent="VoiceKit",
            error_detail="Twilio API returned 429 Too Many Requests. 3 consecutive failures in 60s window.",
            call_sid="CA-demo-005",
            client_id="client-002",
            timestamp="2026-05-31T15:45:00+00:00",
            trace_id="trace-005",
        ),
        EmergencyEvent(
            emergency_id=str(uuid.uuid4()),
            severity="P2",
            agent="LLM-API",
            error_detail="Claude 3 Haiku rate limit exceeded. 5s backoff applied. Degraded response time.",
            timestamp="2026-05-31T14:30:00+00:00",
            trace_id="trace-006",
        ),
    ]
    for alert in demo_alerts:
        svc.push_alert(alert)

    # Seed circuit breaker states via real CB operations
    for agent_name in ("voicekit", "twilio-webhook", "llm-api"):
        cb = svc.register_circuit_breaker(agent_name)
        # Simulate some failures for visual demo
        import time
        now = time.time()
        from localagency.services.circuit_breaker import CircuitBreakerState, CircuitState
        # Manually set state for demo visibility
        state = await cb._load_state()
        if agent_name == "voicekit":
            state.failure_count = 0
            state.state = CircuitState.CLOSED
            state.last_state_change = now
        elif agent_name == "twilio-webhook":
            state.failure_count = 5
            state.state = CircuitState.OPEN
            state.cooldown_until = now + 30
            state.last_state_change = now
        elif agent_name == "llm-api":
            state.failure_count = 2
            state.state = CircuitState.CLOSED
            state.window_start = now - 30
            state.last_state_change = now
        await cb._save_state(state)

    return {"status": "seeded", "calls": len(demo_calls), "alerts": len(demo_alerts)}
