"""Manga token balance operations via Supabase REST / RPC."""

from __future__ import annotations

import os

import httpx
from fastapi import HTTPException


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is required")
    return url.rstrip("/")


def _service_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required")
    return key


def _headers() -> dict[str, str]:
    return {
        "apikey": _service_key(),
        "Authorization": f"Bearer {_service_key()}",
        "Content-Type": "application/json",
    }


async def get_balance(user_id: str) -> int:
    url = f"{_supabase_url()}/rest/v1/user_tokens"
    params = {"user_id": f"eq.{user_id}", "select": "balance"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Supabase error: {resp.text[:500]}")
        rows = resp.json()
    if not rows:
        return 0
    return int(rows[0]["balance"])


async def debit_token(user_id: str, *, reason: str = "generate") -> int:
    url = f"{_supabase_url()}/rest/v1/rpc/debit_manga_token"
    payload = {"p_user_id": user_id, "p_reason": reason}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Supabase debit error: {resp.text[:500]}")
        result = resp.json()
    if result is None:
        raise HTTPException(status_code=402, detail="Insufficient manga tokens")
    return int(result)


async def credit_token(user_id: str, *, amount: int = 1, reason: str = "refund") -> int:
    url = f"{_supabase_url()}/rest/v1/rpc/credit_manga_tokens"
    payload = {"p_user_id": user_id, "p_amount": amount, "p_reason": reason}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Supabase credit error: {resp.text[:500]}")
        return int(resp.json())
