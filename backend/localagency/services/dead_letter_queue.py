"""
localagency/services/dead_letter_queue.py
═══════════════════════════════════════════
Dead Letter Queue with replay capability.

Captures events that exhaust all retries with:
- Full payload snapshot (to allow replay without original source)
- Complete error chain (every error message from every retry)
- Trace ID for correlating with source event
- Replay count to prevent infinite replay loops
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class DeadLetterEntry:
    """
    A single entry in the dead letter queue.
    """
    dlq_entry_id: str
    contract_id: str
    source_agent: str
    target_agent: str
    original_envelope_id: Optional[str] = None
    max_attempts: int = 3
    attempts_made: int = 0
    last_error: str = ""
    error_chain: list[str] = field(default_factory=list)
    payload_snapshot: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    client_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    replayed: bool = False
    replay_count: int = 0
    resolved: bool = False
    resolution_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "dlq_entry_id": self.dlq_entry_id,
            "contract_id": self.contract_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "original_envelope_id": self.original_envelope_id,
            "max_attempts": self.max_attempts,
            "attempts_made": self.attempts_made,
            "last_error": self.last_error,
            "error_chain": self.error_chain,
            "payload_snapshot": self.payload_snapshot,
            "trace_id": self.trace_id,
            "client_id": self.client_id,
            "timestamp": self.timestamp,
            "replayed": self.replayed,
            "replay_count": self.replay_count,
            "resolved": self.resolved,
            "resolution_notes": self.resolution_notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeadLetterEntry:
        return cls(
            dlq_entry_id=data["dlq_entry_id"],
            contract_id=data.get("contract_id", ""),
            source_agent=data.get("source_agent", ""),
            target_agent=data.get("target_agent", ""),
            original_envelope_id=data.get("original_envelope_id"),
            max_attempts=data.get("max_attempts", 3),
            attempts_made=data.get("attempts_made", 0),
            last_error=data.get("last_error", ""),
            error_chain=data.get("error_chain", []),
            payload_snapshot=data.get("payload_snapshot", {}),
            trace_id=data.get("trace_id", ""),
            client_id=data.get("client_id"),
            timestamp=data.get("timestamp", ""),
            replayed=data.get("replayed", False),
            replay_count=data.get("replay_count", 0),
            resolved=data.get("resolved", False),
            resolution_notes=data.get("resolution_notes", ""),
        )


class DeadLetterStore:
    """Abstract interface for DLQ persistence."""

    async def push(self, entry: DeadLetterEntry) -> None:
        raise NotImplementedError

    async def pop(self, dlq_entry_id: str) -> Optional[DeadLetterEntry]:
        raise NotImplementedError

    async def list_entries(
        self, client_id: Optional[str] = None, resolved: Optional[bool] = None, limit: int = 50
    ) -> list[DeadLetterEntry]:
        raise NotImplementedError

    async def mark_resolved(self, dlq_entry_id: str, notes: str = "") -> None:
        raise NotImplementedError

    async def increment_replay(self, dlq_entry_id: str) -> Optional[DeadLetterEntry]:
        raise NotImplementedError

    async def count(self, unresolved_only: bool = True) -> int:
        raise NotImplementedError


class MemoryDeadLetterStore(DeadLetterStore):
    """In-memory store for testing. NOT for production use."""

    def __init__(self) -> None:
        self._entries: dict[str, DeadLetterEntry] = {}

    async def push(self, entry: DeadLetterEntry) -> None:
        self._entries[entry.dlq_entry_id] = entry

    async def pop(self, dlq_entry_id: str) -> Optional[DeadLetterEntry]:
        return self._entries.get(dlq_entry_id)

    async def list_entries(
        self, client_id: Optional[str] = None, resolved: Optional[bool] = None, limit: int = 50
    ) -> list[DeadLetterEntry]:
        results = list(self._entries.values())
        if client_id:
            results = [e for e in results if e.client_id == client_id]
        if resolved is not None:
            results = [e for e in results if e.resolved == resolved]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    async def mark_resolved(self, dlq_entry_id: str, notes: str = "") -> None:
        entry = self._entries.get(dlq_entry_id)
        if entry:
            entry.resolved = True
            entry.resolution_notes = notes

    async def increment_replay(self, dlq_entry_id: str) -> Optional[DeadLetterEntry]:
        entry = self._entries.get(dlq_entry_id)
        if entry:
            entry.replayed = True
            entry.replay_count += 1
        return entry

    async def count(self, unresolved_only: bool = True) -> int:
        if unresolved_only:
            return sum(1 for e in self._entries.values() if not e.resolved)
        return len(self._entries)


class DeadLetterQueue:
    """
    Dead Letter Queue with replay capability.

    Usage:
        dlq = DeadLetterQueue(store=PostgresDeadLetterStore(db_session))
        await dlq.send(entry)
        entries = await dlq.list_unresolved()
        await dlq.replay(entry_id)  # Returns payload for reprocessing
    """

    def __init__(self, store: DeadLetterStore) -> None:
        self._store = store

    async def send(self, entry: DeadLetterEntry) -> None:
        """Send an event to the dead letter queue."""
        await self._store.push(entry)

    async def list_unresolved(self, client_id: Optional[str] = None, limit: int = 50) -> list[DeadLetterEntry]:
        """List all unresolved DLQ entries, optionally filtered by client."""
        return await self._store.list_entries(client_id=client_id, resolved=False, limit=limit)

    async def list_all(
        self, client_id: Optional[str] = None, limit: int = 100
    ) -> list[DeadLetterEntry]:
        """List all DLQ entries (resolved + unresolved)."""
        return await self._store.list_entries(client_id=client_id, limit=limit)

    async def replay(self, dlq_entry_id: str) -> Optional[dict]:
        """
        Replay a DLQ entry. Increments replay counter and returns the payload
        snapshot for the caller to reprocess.
        """
        entry = await self._store.increment_replay(dlq_entry_id)
        if entry is None:
            return None
        return entry.payload_snapshot

    async def resolve(self, dlq_entry_id: str, notes: str = "") -> None:
        """Mark a DLQ entry as resolved (founder reviewed and handled)."""
        await self._store.mark_resolved(dlq_entry_id, notes=notes)

    async def count(self) -> int:
        """Get count of unresolved DLQ entries."""
        return await self._store.count(unresolved_only=True)

    async def get_entry(self, dlq_entry_id: str) -> Optional[DeadLetterEntry]:
        """Get a single DLQ entry by ID."""
        return await self._store.pop(dlq_entry_id)
