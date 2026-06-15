"""OpenRouter proxy for hosted image generation."""

from __future__ import annotations

import os

import httpx
from fastapi import HTTPException

DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required on the server")
    return key


async def forward_generate(payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {_openrouter_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://manga.hosted",
        "X-Title": "manga-hosted",
    }
    url = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_URL)
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter error {resp.status_code}: {resp.text[:1500]}",
        )
    return resp.json()
