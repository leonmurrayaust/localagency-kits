from __future__ import annotations

import os
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

FREE_MODEL = "google/gemma-2-2b-it:free"

async def call_llm(system: str, user: str, model: str = FREE_MODEL) -> str:
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content
