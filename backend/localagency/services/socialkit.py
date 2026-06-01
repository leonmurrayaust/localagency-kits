from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from localagency.services.llm import call_llm

SYSTEM_PROMPT = """You are SocialKit, an AI social media content creator for local trade businesses.
Generate posts that feel authentic, not corporate.
Use the business's voice. Include relevant hashtags.
Each post should educate, entertain, or build trust - not just sell."""

async def generate_social_post(
    business_name: str,
    vertical: str,
    topic: str = "",
    season: str = "",
    style: str = "educational",
) -> str:
    user = json.dumps({
        "task": "Write a social media post",
        "business_name": business_name,
        "vertical": vertical,
        "topic": topic or f"common {vertical} tips",
        "season": season or "current season",
        "style": style,
        "instructions": (
            "Write one Facebook/Instagram post (200-300 characters). "
            "Include 3-5 relevant hashtags. "
            f"If style is educational: share a helpful tip related to {vertical}. "
            "If style is promotional: highlight a service with a clear CTA. "
            "If style is social-proof: describe a recent job and happy customer. "
            "Make it sound like a real person, not an agency."
        ),
    })
    return await call_llm(SYSTEM_PROMPT, user)


async def generate_post_batch(
    business_name: str,
    vertical: str,
    count: int = 4,
    season: str = "",
) -> list[str]:
    user = json.dumps({
        "task": f"Generate {count} social media posts for the coming week",
        "business_name": business_name,
        "vertical": vertical,
        "season": season or "current season",
        "count": count,
        "instructions": (
            f"Write exactly {count} distinct posts. "
            f"Mix of educational tips, customer stories, seasonal advice, and service highlights. "
            "Return as a JSON array of strings. Each post 200-300 characters with hashtags."
        ),
    })
    result = await call_llm(SYSTEM_PROMPT, user)
    try:
        posts = json.loads(result)
        if isinstance(posts, list):
            return posts[:count]
    except (json.JSONDecodeError, TypeError):
        pass
    return [result]
