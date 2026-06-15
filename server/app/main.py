"""Manga hosted provider API — auth-gated OpenRouter proxy with token billing."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import AuthUser, require_user
from app.proxy import forward_generate
from app.tokens import credit_token, debit_token, get_balance
from app.web import router as web_router

app = FastAPI(title="Manga Hosted Provider", version="0.1.0")
app.include_router(web_router)


class MeResponse(BaseModel):
    user_id: str
    email: str | None
    manga_tokens: int


class GenerateRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    max_tokens: int = Field(default=16384, ge=1)
    modalities: list[str] | None = None
    image_config: dict[str, Any] | None = None


def _response_images(result: dict[str, Any]) -> list[Any]:
    choices = result.get("choices") or []
    message = (choices[0] if choices else {}).get("message") or {}
    return message.get("images") or []


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/me", response_model=MeResponse)
async def me(user: AuthUser = Depends(require_user)) -> MeResponse:
    balance = await get_balance(user.user_id)
    return MeResponse(user_id=user.user_id, email=user.email, manga_tokens=balance)


@app.post("/v1/generate")
async def generate(body: GenerateRequest, user: AuthUser = Depends(require_user)) -> dict[str, Any]:
    if body.stream:
        raise HTTPException(status_code=400, detail="stream is not supported")

    await debit_token(user.user_id, reason="generate")
    payload = body.model_dump(exclude_none=True)

    try:
        result = await forward_generate(payload)
    except HTTPException:
        await credit_token(user.user_id, amount=1, reason="generate_refund")
        raise

    if not _response_images(result):
        await credit_token(user.user_id, amount=1, reason="generate_no_image")
        raise HTTPException(status_code=502, detail="OpenRouter returned no image")

    return result
