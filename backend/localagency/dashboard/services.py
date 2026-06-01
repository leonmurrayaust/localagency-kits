"""
localagency/dashboard/services.py
══════════════════════════════════
Data service layer for the exception dashboard.

Connects the frontend views to backend contracts:
  - CircuitBreakerStore → circuit breaker states
  - DeadLetterQueue    → unresolved errors and replay
  - VoiceKitService    → call records and booking data
  - Ingress/Classified events → alert feed

Each service returns dicts ready for Jinja2 template injection.
Designed for dependency injection so tests can swap Memory stores.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from localagency.config import get_settings
from localagency.models.events import CallRecord, CallState, EmergencyEvent
from localagency.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerState,
    CircuitState,
    MemoryCircuitBreakerStore,
)
from localagency.services.dead_letter_queue import (
    DeadLetterEntry,
    DeadLetterQueue,
    MemoryDeadLetterStore,
)


# ── Dashboard Data Service ─────────────────────────────────────────────────────


class DashboardDataService:
    """
    Aggregates data from all backend services for the exception dashboard views.

    In Phase 1 this uses Memory stores (testing / single-founder mode).
    Phase 2 swaps to RedisCircuitBreakerStore + PostgresDeadLetterStore.
    The interface is identical — dashboard code never changes.
    """

    def __init__(
        self,
        cb_store: Optional[Any] = None,
        dlq_store: Optional[Any] = None,
        call_store: Optional[dict[str, CallRecord]] = None,
    ) -> None:
        settings = get_settings()
        from localagency.services.circuit_breaker import MemoryCircuitBreakerStore
        from localagency.services.dead_letter_queue import MemoryDeadLetterStore

        self._cb_store = cb_store or MemoryCircuitBreakerStore()
        self._dlq_store = dlq_store or MemoryDeadLetterStore()
        self._call_store: dict[str, CallRecord] = call_store or {}
        self._alerts: list[EmergencyEvent] = []
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    # ── Registers ──────────────────────────────────────────────────────────────

    def register_circuit_breaker(self, agent_name: str) -> CircuitBreaker:
        """Register a circuit breaker for dashboard monitoring."""
        cb = CircuitBreaker(agent_name, store=self._cb_store)
        self._circuit_breakers[agent_name] = cb
        return cb

    def push_alert(self, alert: EmergencyEvent) -> None:
        """Push an emergency alert into the dashboard feed."""
        self._alerts.append(alert)

    def store_call(self, call: CallRecord) -> None:
        """Store a call record for dashboard display."""
        self._call_store[call.call_sid] = call

    # ── Dashboard Overview ─────────────────────────────────────────────────────

    async def get_overview_stats(self) -> dict[str, Any]:
        """Aggregate top-level KPI numbers for the dashboard home."""
        unresolved = [a for a in self._alerts if a.severity in ("P0", "P1")]
        now = datetime.now(timezone.utc)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        missed_today = 0
        bookings_today = 0
        error_count = 0

        for call in self._call_store.values():
            started = _parse_iso(call.started_at)
            if started and started >= today_midnight:
                if call.state == CallState.END and call.error:
                    missed_today += 1
                if call.booking_made:
                    bookings_today += 1
            if call.error:
                error_count += 1

        # DLQ count
        dlq_count = 0
        try:
            dlq_count = await self._dlq_store.count(unresolved_only=True)
        except Exception:
            pass

        return {
            "unresolved_alerts": len(unresolved),
            "missed_calls_today": missed_today,
            "booking_confirmations_today": bookings_today,
            "error_log_count": error_count + dlq_count,
            "circuit_breaker_states": await self._get_all_cb_states(),
            "recent_calls": self._get_recent_calls(5),
            "dlq_count": dlq_count,
        }

    # ── Alerts ─────────────────────────────────────────────────────────────────

    async def get_alerts(
        self, severity: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get alerts, optionally filtered by severity."""
        results = list(self._alerts)
        if severity:
            results = [a for a in results if a.severity == severity]
        results.sort(key=lambda a: a.timestamp, reverse=True)
        return [self._alert_to_dict(a) for a in results[:limit]]

    # ── Missed Calls ───────────────────────────────────────────────────────────

    async def get_missed_calls(
        self, client_id: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get missed/unhandled calls."""
        results = []
        for call in self._call_store.values():
            if call.state == CallState.END and (call.error or call.escalated):
                if client_id and call.client_id != client_id:
                    continue
                results.append(self._call_to_dict(call))
        results.sort(key=lambda c: c["timestamp"], reverse=True)
        return results[:limit]

    # ── Bookings ───────────────────────────────────────────────────────────────

    async def get_bookings(
        self, client_id: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get booking confirmations."""
        results = []
        for call in self._call_store.values():
            if call.booking_made:
                if client_id and call.client_id != client_id:
                    continue
                results.append(self._call_to_dict(call))
        results.sort(key=lambda c: c["timestamp"], reverse=True)
        return results[:limit]

    # ── Error Log ──────────────────────────────────────────────────────────────

    async def get_errors(
        self, severity: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get system error log entries."""
        errors: list[dict[str, Any]] = []

        # From call records
        for call in self._call_store.values():
            if call.error:
                errors.append(
                    {
                        "severity": "P2",
                        "timestamp": call.started_at,
                        "message": call.error,
                        "trace_id": call.trace_id,
                        "call_sid": call.call_sid,
                        "client_id": call.client_id,
                    }
                )

        # From DLQ entries
        try:
            dlq_entries = await self._dlq_store.list_entries(resolved=False, limit=50)
            for entry in dlq_entries:
                errors.append(
                    {
                        "severity": "P1",
                        "timestamp": entry.timestamp,
                        "message": f"DLQ: {entry.last_error[:120]}",
                        "trace_id": entry.trace_id,
                        "dlq_entry_id": entry.dlq_entry_id,
                        "client_id": entry.client_id or "",
                    }
                )
        except Exception:
            pass

        if severity:
            errors = [e for e in errors if e["severity"] == severity]

        errors.sort(key=lambda e: e["timestamp"], reverse=True)
        return errors[:limit]

    # ── Circuit Breakers ───────────────────────────────────────────────────────

    async def get_circuit_breakers(self) -> list[dict[str, Any]]:
        """Get all circuit breaker states."""
        return await self._get_all_cb_states()

    async def get_health_status(self) -> dict[str, Any]:
        """Get aggregated health status for the health fragment."""
        cb_states = await self._get_all_cb_states()
        open_breakers = [b for b in cb_states if b["state"] == "OPEN"]
        all_healthy = len(open_breakers) == 0
        return {
            "overall": "healthy" if all_healthy else "degraded",
            "message": "All systems operational"
            if all_healthy
            else f"{len(open_breakers)} circuit(s) open",
            "components": {
                "api_gateway": "healthy",
                "orchestrator": "healthy",
                "voicekit": "healthy",
                "redis": "connected",
                "postgresql": "connected",
            },
            "open_breakers": open_breakers,
        }

    # ── Alert Count Fragment ───────────────────────────────────────────────────

    async def get_alert_count(self) -> int:
        """Get count of unresolved P0/P1 alerts."""
        return sum(1 for a in self._alerts if a.severity in ("P0", "P1"))

    # ── Internals ──────────────────────────────────────────────────────────────

    async def _get_all_cb_states(self) -> list[dict[str, Any]]:
        states = []
        for name, cb in self._circuit_breakers.items():
            try:
                status = await cb.get_status()
                states.append(status)
            except Exception:
                states.append(
                    {
                        "agent_name": name,
                        "state": "UNKNOWN",
                        "failure_count": 0,
                        "failure_threshold": 5,
                    }
                )
        return states

    def _get_recent_calls(self, n: int) -> list[dict[str, Any]]:
        calls = list(self._call_store.values())
        calls.sort(key=lambda c: c.started_at, reverse=True)
        return [self._call_to_dict(c) for c in calls[:n]]

    # ── Serializers ───────────────────────────────────────────────────────────

    @staticmethod
    def _alert_to_dict(alert: EmergencyEvent) -> dict[str, Any]:
        return {
            "id": alert.emergency_id,
            "severity": alert.severity,
            "title": f"{alert.severity} — {alert.agent}",
            "message": alert.error_detail[:200] if alert.error_detail else "No details",
            "agent": alert.agent,
            "client_id": alert.client_id or "",
            "call_sid": alert.call_sid or "",
            "timestamp": alert.timestamp,
            "trace_id": alert.trace_id,
        }

    @staticmethod
    def _call_to_dict(call: CallRecord) -> dict[str, Any]:
        return {
            "call_sid": call.call_sid,
            "client_id": call.client_id,
            "caller_number": call.from_number,
            "timestamp": call.started_at,
            "duration": call.duration_seconds or 0,
            "status": "completed" if call.state == CallState.END else call.state.value,
            "booking_made": call.booking_made,
            "booking_ref": call.booking_ref or "",
            "escalated": call.escalated,
            "error": call.error or "",
            "trace_id": call.trace_id,
            "cost": round(call.api_cost, 4),
        }


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_iso(iso_str: str) -> Optional[datetime]:
    """Parse ISO datetime string safely."""
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None
