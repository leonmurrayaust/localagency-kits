from __future__ import annotations

import json
from typing import Optional

from localagency.services.llm import call_llm

SYSTEM_PROMPT = """You are LeadKit, an AI lead generation assistant for local service businesses.
You scan social media for people asking for recommendations, and craft warm, helpful DMs.
Never be pushy or salesy. Always lead with value and helpful information."""

async def generate_dm(
    business_name: str,
    vertical: str,
    prospect_name: str = "",
    request_context: str = "",
) -> str:
    user = json.dumps({
        "task": "Write a direct message to someone asking for recommendations",
        "business_name": business_name,
        "vertical": vertical,
        "prospect_name": prospect_name or "there",
        "what_they_asked": request_context or f"looking for {vertical} services",
        "instructions": (
            "Warm, helpful, personal tone. 200 character max for DMs. "
            f"Mention you saw they were looking for {vertical} services. "
            f"Briefly explain how {business_name} helps. "
            "End with a soft CTA: 'Happy to answer any questions!' or similar. "
            "Do NOT include links. Do NOT be pushy. "
            "Reads like a neighbor helping a neighbor."
        ),
    })
    return await call_llm(SYSTEM_PROMPT, user)

async def score_lead(lead_text: str, vertical: str) -> dict:
    user = json.dumps({
        "task": "Score this lead opportunity",
        "lead_text": lead_text,
        "vertical": vertical,
        "instructions": (
            "Analyze the text and return a JSON object with: "
            "score (0-100), reason (one sentence), urgency (low/medium/high). "
            "High urgency = person needs service right now. "
            "Medium = researching. Low = just browsing."
        ),
    })
    result = await call_llm(SYSTEM_PROMPT, user)
    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return {"score": 50, "reason": "could not analyze", "urgency": "medium"}
