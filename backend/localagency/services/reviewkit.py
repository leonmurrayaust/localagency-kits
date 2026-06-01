from __future__ import annotations

import json
from typing import Optional

from localagency.services.llm import call_llm

SYSTEM_PROMPT = """You are ReviewKit, an AI review response assistant for local service businesses.
Generate professional, empathetic responses to customer reviews.
Always match the tone of the review - warm for positive, apologetic for negative.
Keep responses under 150 words. Never be defensive or argumentative."""

async def generate_review_response(
    review_text: str,
    rating: int,
    business_name: str,
    reviewer_name: str = "",
) -> str:
    user = json.dumps({
        "task": "Write a response to this customer review",
        "business_name": business_name,
        "reviewer_name": reviewer_name or "valued customer",
        "rating": rating,
        "review_text": review_text,
        "instructions": (
            "If rating is 4-5: thank them warmly, mention something specific from their review. "
            "If rating is 1-3: apologize sincerely, acknowledge their concern, "
            "invite them to contact directly to make it right. "
            "Never make excuses. Never mention the rating number."
        ),
    })
    return await call_llm(SYSTEM_PROMPT, user)


async def generate_review_request_sms(
    business_name: str,
    service_provided: str,
) -> str:
    user = json.dumps({
        "task": "Write an SMS asking this customer to leave a Google review",
        "business_name": business_name,
        "service_provided": service_provided,
        "instructions": (
            "Friendly, personal tone. 160 character limit. "
            "Include a direct Google review link placeholder: [REVIEW_LINK]"
        ),
    })
    return await call_llm(SYSTEM_PROMPT, user)
