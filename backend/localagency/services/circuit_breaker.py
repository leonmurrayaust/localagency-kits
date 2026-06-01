"""
localagency/services/circuit_breaker.py
══════════════════════════════════════════
Per-agent circuit breaker with 3-state (CLOSED/OPEN/HALF_OPEN).

State machine:
  CLOSED ──(5 failures in 60s window)──▶ OPEN
  OPEN ──(30s cooldown expires)──▶ HALF_OPEN
  HALF_OPEN ──(test succeeds)──▶ CLOSED
  HALF_OPEN ──(test fails)──▶ OPEN

State is persisted in Redis (not local memory) for process-restart resilience.
Circuit breaker state is the ONLY memory that survives process restart.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CircuitState(str, Enum):
    """Three-state circuit breaker."""
    CLOSED = "CLOSED"          # Normal operation — requests pass through
    OPEN = "OPEN"              # Failing — requests fast-fail
    HALF_OPEN = "HALF_OPEN"    # Testing — one request allowed through


@dataclass
class CircuitBreakerState:
    """
    Complete state snapshot for one circuit breaker instance.
    All fields are serializable for Redis persistence.
    """
    agent_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0  # Unix timestamp
    window_start: float = 0.0       # Unix timestamp of rolling window start
    last_state_change: float = 0.0  # Unix timestamp
    cooldown_until: float = 0.0     # Unix timestamp when OPEN→HALF_OPEN is allowed

    # Config (set at init, not changed during operation)
    failure_threshold: int = 5
    window_seconds: int = 60
    cooldown_seconds: int = 30

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "window_start": self.window_start,
            "last_state_change": self.last_state_change,
            "cooldown_until": self.cooldown_until,
            "failure_threshold": self.failure_threshold,
            "window_seconds": self.window_seconds,
            "cooldown_seconds": self.cooldown_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CircuitBreakerState:
        return cls(
            agent_name=data["agent_name"],
            state=CircuitState(data["state"]),
            failure_count=data.get("failure_count", 0),
            last_failure_time=data.get("last_failure_time", 0.0),
            window_start=data.get("window_start", 0.0),
            last_state_change=data.get("last_state_change", 0.0),
            cooldown_until=data.get("cooldown_until", 0.0),
            failure_threshold=data.get("failure_threshold", 5),
            window_seconds=data.get("window_seconds", 60),
            cooldown_seconds=data.get("cooldown_seconds", 30),
        )


class CircuitBreakerStore:
    """
    Abstract store interface for circuit breaker state persistence.
    Implementations: RedisCircuitBreakerStore (production), MemoryCircuitBreakerStore (testing).
    """

    async def get_state(self, agent_name: str) -> Optional[CircuitBreakerState]:
        raise NotImplementedError

    async def set_state(self, state: CircuitBreakerState) -> None:
        raise NotImplementedError

    async def clear_state(self, agent_name: str) -> None:
        raise NotImplementedError


class MemoryCircuitBreakerStore(CircuitBreakerStore):
    """In-memory store for testing. NOT for production use."""

    def __init__(self) -> None:
        self._store: dict[str, CircuitBreakerState] = {}

    async def get_state(self, agent_name: str) -> Optional[CircuitBreakerState]:
        return self._store.get(agent_name)

    async def set_state(self, state: CircuitBreakerState) -> None:
        self._store[state.agent_name] = state

    async def clear_state(self, agent_name: str) -> None:
        self._store.pop(agent_name, None)


class CircuitBreakerError(Exception):
    """Raised when a circuit is OPEN and a request is rejected."""
    pass


class CircuitBreaker:
    """
    Per-agent circuit breaker with rolling failure window and automatic recovery.

    Usage:
        cb = CircuitBreaker("voicekit-twilio", store=RedisCircuitBreakerStore(redis))
        async with cb:
            result = await call_twilio_api()
    """

    def __init__(
        self,
        agent_name: str,
        failure_threshold: int = 5,
        window_seconds: int = 60,
        cooldown_seconds: int = 30,
        store: Optional[CircuitBreakerStore] = None,
    ) -> None:
        self.agent_name = agent_name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._store = store or MemoryCircuitBreakerStore()

    async def _load_state(self) -> CircuitBreakerState:
        state = await self._store.get_state(self.agent_name)
        if state is None:
            state = CircuitBreakerState(
                agent_name=self.agent_name,
                failure_threshold=self.failure_threshold,
                window_seconds=self.window_seconds,
                cooldown_seconds=self.cooldown_seconds,
            )
        return state

    async def _save_state(self, state: CircuitBreakerState) -> None:
        await self._store.set_state(state)

    async def allow_request(self) -> bool:
        """
        Check whether a request is allowed through the circuit breaker.

        Returns True if the circuit is CLOSED or in HALF_OPEN test mode.
        Returns False if OPEN (fast-fail).
        """
        state = await self._load_state()
        now = time.time()

        if state.state == CircuitState.CLOSED:
            # Check if rolling window has expired — reset if so
            if now - state.window_start > state.window_seconds:
                state.failure_count = 0
                state.window_start = now
                await self._save_state(state)
            return True

        elif state.state == CircuitState.OPEN:
            # Check if cooldown has expired → transition to HALF_OPEN
            if now >= state.cooldown_until:
                state.state = CircuitState.HALF_OPEN
                state.last_state_change = now
                await self._save_state(state)
                return True  # Allow test request
            return False

        elif state.state == CircuitState.HALF_OPEN:
            # Allow one test request through
            return True

        return False

    async def record_success(self) -> None:
        """Record a successful request. Resets failure count, closes circuit."""
        state = await self._load_state()

        if state.state == CircuitState.HALF_OPEN:
            # Test request succeeded → close circuit
            state.state = CircuitState.CLOSED
            state.failure_count = 0
            state.window_start = time.time()
            state.last_state_change = time.time()
            await self._save_state(state)

    async def record_failure(self) -> None:
        """
        Record a failed request.
        Increments failure count and may open the circuit.
        """
        state = await self._load_state()
        now = time.time()

        state.failure_count += 1
        state.last_failure_time = now

        if state.state == CircuitState.HALF_OPEN:
            # Test request failed → back to OPEN
            state.state = CircuitState.OPEN
            state.cooldown_until = now + state.cooldown_seconds
            state.last_state_change = now
        elif state.state == CircuitState.CLOSED:
            # Check if window has expired — if so, start new window
            if now - state.window_start > state.window_seconds:
                state.failure_count = 1
                state.window_start = now
            elif state.failure_count >= state.failure_threshold:
                # Threshold crossed → open circuit
                state.state = CircuitState.OPEN
                state.cooldown_until = now + state.cooldown_seconds
                state.last_state_change = now

        await self._save_state(state)

    async def get_status(self) -> dict:
        """Get current status for monitoring / health endpoints."""
        state = await self._load_state()
        return {
            "agent_name": state.agent_name,
            "state": state.state.value,
            "failure_count": state.failure_count,
            "failure_threshold": state.failure_threshold,
            "window_seconds": state.window_seconds,
            "cooldown_seconds": state.cooldown_seconds,
            "is_allowing": state.state != CircuitState.OPEN or time.time() >= state.cooldown_until,
            "last_state_change": datetime.fromtimestamp(
                state.last_state_change, tz=timezone.utc
            ).isoformat() if state.last_state_change else None,
        }

    async def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        state = CircuitBreakerState(
            agent_name=self.agent_name,
            failure_threshold=self.failure_threshold,
            window_seconds=self.window_seconds,
            cooldown_seconds=self.cooldown_seconds,
        )
        await self._save_state(state)

    async def __aenter__(self) -> "CircuitBreaker":
        if not await self.allow_request():
            raise CircuitBreakerError(
                f"Circuit breaker OPEN for agent '{self.agent_name}'"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None and exc_type is not CircuitBreakerError:
            await self.record_failure()
        else:
            await self.record_success()
