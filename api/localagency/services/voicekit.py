"""
localagency/services/voicekit.py
══════════════════════════════════
VoiceKit — AI Receptionist Call State Machine.

Implements the LangGraph-based call flow for inbound phone calls:
  INBOUND_CALL → IVR_GREETING → LLM_INTENT_CLASSIFY → [branch]
    → booking: CALENDAR_CHECK → SLOT_OFFER → CONFIRM_BOOKING → SMS_CONFIRM → END
    → after_hours: VOICEMAIL_CAPTURE → TRANSCRIBE → SMS_OWNER → END
    → emergency: ESCALATE_HUMAN → ALERT_FOUNDER → END
    → faq: ANSWER_FROM_KB → OFFER_BOOKING → END | BOOKING
    → low_confidence: TRANSFER_HUMAN → LOG → END
    → dropped: SMS_RESUME_LINK → END
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from localagency.config import get_settings
from localagency.models.events import CallRecord, CallState, IntentCategory
from localagency.services.circuit_breaker import CircuitBreaker, MemoryCircuitBreakerStore


# ── State Handlers ────────────────────────────────────────────────────────────
# Each handler is a callable that takes context and returns (next_state, output).

class StateHandler:
    """Base interface for a call state handler."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        raise NotImplementedError


class GreetingHandler(StateHandler):
    """Play business greeting, then move to intent classification."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        greeting_text = context.get("greeting", "Thank you for calling. How can I help you today?")
        return CallState.LLM_INTENT_CLASSIFY, {
            "twiml": f"<Say>{greeting_text}</Say>",
            "greeting_played": True,
        }


class InboundCallHandler(StateHandler):
    """Initial inbound call — transition to IVR greeting."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        return CallState.IVR_GREETING, {"call_started": True}


class IntentClassifyHandler(StateHandler):
    """
    Classify caller intent via LLM (or simulated for Phase 1).
    Returns the next state based on intent classification.
    """
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        # Simulated LLM classification for Phase 1
        # In Phase 2, this calls Claude 3 Haiku via API
        transcription = context.get("transcription", "")
        intent = self._simulate_classify(transcription)

        call.intent = intent

        if intent == IntentCategory.BOOKING_REQUEST:
            return CallState.BOOKING_INTENT, {"intent": "booking", "confidence": 0.85}
        elif intent == IntentCategory.AFTER_HOURS:
            return CallState.AFTER_HOURS, {"intent": "after_hours"}
        elif intent == IntentCategory.EMERGENCY:
            return CallState.EMERGENCY, {"intent": "emergency"}
        elif intent == IntentCategory.FAQ_QUERY:
            return CallState.FAQ_QUERY, {"intent": "faq"}
        else:
            return CallState.LOW_CONFIDENCE, {"intent": "low_confidence", "confidence": 0.45}

    def _simulate_classify(self, text: str) -> IntentCategory:
        """Simple keyword-based intent classification for development."""
        if not text:
            return IntentCategory.FAQ_QUERY
        text_lower = text.lower()
        if any(w in text_lower for w in ("emergency", "urgent", "burst pipe", "flood", "fire", "gas leak")):
            return IntentCategory.EMERGENCY
        if any(w in text_lower for w in ("book", "appointment", "schedule", "when can", "available")):
            return IntentCategory.BOOKING_REQUEST
        if any(w in text_lower for w in ("price", "cost", "how much", "service", "hours")):
            return IntentCategory.FAQ_QUERY
        return IntentCategory.BOOKING_REQUEST


class BookingHandler(StateHandler):
    """Handle booking intent — check calendar, offer slots, confirm."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        # TODO: Call Calendly API for real slot availability
        return CallState.CONFIRM_BOOKING, {
            "slots": ["Monday 10:00 AM", "Monday 2:00 PM", "Tuesday 9:00 AM"],
            "booking_ref": str(uuid.uuid4())[:8].upper(),
        }


class ConfirmBookingHandler(StateHandler):
    """Confirm booking with caller and send SMS."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        booking_ref = context.get("booking_ref", "")
        selected_slot = context.get("selected_slot", "Monday 10:00 AM")

        call.booking_made = True
        call.booking_ref = booking_ref

        return CallState.SMS_CONFIRM, {
            "booking_ref": booking_ref,
            "selected_slot": selected_slot,
            "sms_text": f"Your appointment is confirmed for {selected_slot}. Ref: {booking_ref}",
        }


class AfterHoursHandler(StateHandler):
    """Capture voicemail after hours, send SMS transcript to owner."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        return CallState.SMS_OWNER, {
            "voicemail_captured": True,
            "owner_sms": "Missed call after hours. Playing voicemail prompt.",
        }


class EmergencyHandler(StateHandler):
    """Escalate to founder immediately with full context."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        call.escalated = True
        return CallState.ALERT_FOUNDER, {
            "emergency_type": context.get("emergency_type", "unknown"),
            "founder_alert": "P0: Emergency call — immediate callback required",
        }


class FaqHandler(StateHandler):
    """Answer FAQ from knowledge base, then offer booking."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        return CallState.OFFER_BOOKING, {
            "answer": "We serve the Phoenix metro area. Our prices vary by service — I can have someone call you with a quote. Would you like to book an appointment?",
        }


class LowConfidenceHandler(StateHandler):
    """Low-confidence classification — transfer to founder or take voicemail."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        call.escalated = True
        return CallState.END, {
            "action": "transfer_to_human",
            "reason": "Low classification confidence",
        }


class EndHandler(StateHandler):
    """Terminal state — log call record."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        call.state = CallState.END
        call.ended_at = datetime.now(timezone.utc).isoformat()
        return CallState.END, {"completed": True}


class OfferBookingHandler(StateHandler):
    """Offer booking after FAQ — then end call."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        return CallState.END, {"booking_offered": True}


class AnswerFromKbHandler(StateHandler):
    """Answer from knowledge base, then offer booking."""
    async def handle(self, call: CallRecord, context: dict[str, Any]) -> tuple[CallState, dict[str, Any]]:
        return CallState.OFFER_BOOKING, {"answered": True}


# ── State Machine Map ─────────────────────────────────────────────────────────

STATE_HANDLERS: dict[CallState, StateHandler] = {
    CallState.INBOUND_CALL: InboundCallHandler(),
    CallState.IVR_GREETING: GreetingHandler(),
    CallState.LLM_INTENT_CLASSIFY: IntentClassifyHandler(),
    CallState.BOOKING_INTENT: BookingHandler(),
    CallState.CONFIRM_BOOKING: ConfirmBookingHandler(),
    CallState.AFTER_HOURS: AfterHoursHandler(),
    CallState.EMERGENCY: EmergencyHandler(),
    CallState.FAQ_QUERY: FaqHandler(),
    CallState.ANSWER_FROM_KB: AnswerFromKbHandler(),
    CallState.LOW_CONFIDENCE: LowConfidenceHandler(),
    CallState.OFFER_BOOKING: OfferBookingHandler(),
    CallState.END: EndHandler(),
}

# State transition map — valid next states from each state
STATE_TRANSITIONS: dict[CallState, list[CallState]] = {
    CallState.INBOUND_CALL: [CallState.IVR_GREETING],
    CallState.IVR_GREETING: [CallState.LLM_INTENT_CLASSIFY],
    CallState.LLM_INTENT_CLASSIFY: [
        CallState.BOOKING_INTENT,
        CallState.AFTER_HOURS,
        CallState.EMERGENCY,
        CallState.FAQ_QUERY,
        CallState.LOW_CONFIDENCE,
        CallState.DROPPED_MID_FLOW,
    ],
    CallState.BOOKING_INTENT: [CallState.CALENDAR_CHECK, CallState.SLOT_OFFER, CallState.CONFIRM_BOOKING],
    CallState.CALENDAR_CHECK: [CallState.SLOT_OFFER],
    CallState.SLOT_OFFER: [CallState.CONFIRM_BOOKING],
    CallState.CONFIRM_BOOKING: [CallState.SMS_CONFIRM, CallState.END],
    CallState.SMS_CONFIRM: [CallState.END],
    CallState.AFTER_HOURS: [CallState.VOICEMAIL_CAPTURE, CallState.TRANSCRIBE, CallState.SMS_OWNER, CallState.END],
    CallState.VOICEMAIL_CAPTURE: [CallState.TRANSCRIBE],
    CallState.TRANSCRIBE: [CallState.SMS_OWNER, CallState.END],
    CallState.SMS_OWNER: [CallState.END],
    CallState.EMERGENCY: [CallState.ESCALATE_HUMAN, CallState.ALERT_FOUNDER, CallState.END],
    CallState.ESCALATE_HUMAN: [CallState.ALERT_FOUNDER, CallState.END],
    CallState.ALERT_FOUNDER: [CallState.END],
    CallState.FAQ_QUERY: [CallState.ANSWER_FROM_KB, CallState.OFFER_BOOKING, CallState.END],
    CallState.ANSWER_FROM_KB: [CallState.OFFER_BOOKING, CallState.END],
    CallState.OFFER_BOOKING: [CallState.BOOKING_INTENT, CallState.END],
    CallState.LOW_CONFIDENCE: [CallState.TRANSFER_HUMAN, CallState.LOG, CallState.END],
    CallState.TRANSFER_HUMAN: [CallState.LOG, CallState.END],
    CallState.LOG: [CallState.END],
    CallState.DROPPED_MID_FLOW: [CallState.SMS_RESUME_LINK, CallState.END],
    CallState.SMS_RESUME_LINK: [CallState.END],
    CallState.END: [],
}


# ── VoiceKit Service ──────────────────────────────────────────────────────────

class VoiceKitService:
    """
    VoiceKit AI Receptionist service.

    Orchestrates the LangGraph call state machine for each inbound call.
    Each call gets a CallRecord that persists across state transitions.
    """

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        state_handlers: Optional[dict[CallState, StateHandler]] = None,
    ) -> None:
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            "voicekit",
            store=MemoryCircuitBreakerStore(),
        )
        self._handlers = state_handlers or STATE_HANDLERS
        self._transitions = STATE_TRANSITIONS

    async def process_call(self, call: CallRecord) -> dict[str, Any]:
        """
        Process an inbound call through the state machine.

        Args:
            call: Initial call record with at minimum call_sid, from_number, client_id

        Returns:
            Final output context with results
        """
        if not await self._circuit_breaker.allow_request():
            return {
                "error": "Circuit breaker OPEN — VoiceKit unavailable",
                "call_sid": call.call_sid,
                "fallback": "voicemail",
            }

        context: dict[str, Any] = {}
        max_steps = 20  # Safety limit to prevent infinite loops
        step = 0

        current_state = call.state

        while current_state != CallState.END and step < max_steps:
            step += 1
            handler = self._handlers.get(current_state)
            if handler is None:
                context["error"] = f"No handler for state: {current_state}"
                break

            try:
                next_state, output = await handler.handle(call, context)
                context.update(output)
                call.state = next_state

                # Validate transition
                if next_state not in self._transitions.get(current_state, []):
                    context["warning"] = f"Unexpected transition: {current_state.value} → {next_state.value}"
                    # Allow it — state machine is permissive in Phase 1

                current_state = next_state
            except Exception as e:
                context["error"] = str(e)
                call.error = str(e)
                current_state = CallState.END

        call.ended_at = datetime.now(timezone.utc).isoformat()
        context["call_record"] = call
        context["steps"] = step

        await self._circuit_breaker.record_success()

        return context

    async def handle_inbound_call(
        self,
        call_sid: str,
        from_number: str,
        client_id: str = "",
        greeting: str = "",
    ) -> dict[str, Any]:
        """
        Handle a new inbound call from start to finish.

        This is the main entry point for the Twilio voice webhook handler.
        """
        call = CallRecord(
            call_sid=call_sid,
            client_id=client_id,
            from_number=from_number,
            to_number="",
            state=CallState.INBOUND_CALL,
            trace_id=str(uuid.uuid4()),
        )

        context = await self.process_call(call)
        return context

    async def get_call_status(self, call_sid: str) -> Optional[CallRecord]:
        """Get the current status of a call (for dashboard polling)."""
        # TODO: Read from PostgreSQL/Redis
        return None
