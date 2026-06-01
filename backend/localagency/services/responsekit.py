from __future__ import annotations

import json
from typing import Optional

from localagency.services.llm import call_llm

SYSTEM_PROMPT = """You are ResponseKit, an AI lead response assistant for local service businesses.
Respond to customer inquiries quickly and helpfully.
Always capture the key information needed to book the job.
Never sound like a bot. Be warm and efficient."""

async def generate_lead_response(
    inquiry: str,
    business_name: str,
    vertical: str,
    source: str = "",
    customer_name: str = "",
) -> str:
    user = json.dumps({
        "task": "Write a response to a customer inquiry",
        "business_name": business_name,
        "vertical": vertical,
        "customer_name": customer_name or "there",
        "inquiry": inquiry,
        "source": source or "website",
        "instructions": (
            "Respond within 60 seconds (sub-60s speed-to-lead). "
            "Thank them for reaching out. Address their specific question. "
            "Ask for their phone number and best time to call if needed. "
            "Keep it to 2-3 sentences. Warm and professional. "
            "If they're asking for a quote: acknowledge and ask for details to provide accurate estimate."
        ),
    })
    return await call_llm(SYSTEM_PROMPT, user)


async def generate_follow_up(
    previous_exchange: str,
    days_since: int = 3,
    business_name: str = "",
) -> str:
    user = json.dumps({
        "task": "Write a follow-up message to a lead",
        "business_name": business_name or "our team",
        "days_since_last_contact": days_since,
        "previous_exchange": previous_exchange,
        "instructions": (
            f"It's been {days_since} days since we last spoke. "
            "Check in warmly. Don't be pushy. "
            "Offer a specific next step: 'Still need help with that?' or "
            "'We have availability this Thursday if you'd like to schedule.' "
            "2-3 sentences max."
        ),
    })
    return await call_llm(SYSTEM_PROMPT, user)
