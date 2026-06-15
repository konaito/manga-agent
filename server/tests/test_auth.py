"""Tests for Supabase JWT auth."""

from __future__ import annotations

import os
import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-unit-tests")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")

from app.auth import AuthUser, decode_access_token, require_user  # noqa: E402


def _token(*, sub: str = "user-1", email: str | None = "user@example.com", extra: dict | None = None) -> str:
    payload = {
        "sub": sub,
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    if email is not None:
        payload["email"] = email
    if extra:
        payload.update(extra)
    return jwt.encode(payload, os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")


@pytest.mark.asyncio
async def test_require_user_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc:
        await require_user(None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_rejects_non_bearer_scheme():
    creds = HTTPAuthorizationCredentials(scheme="Basic", credentials="x")
    with pytest.raises(HTTPException) as exc:
        await require_user(creds)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_returns_auth_user():
    token = _token()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    user = await require_user(creds)
    assert user == AuthUser(user_id="user-1", email="user@example.com")


def test_decode_access_token_invalid():
    with pytest.raises(HTTPException) as exc:
        decode_access_token("not-a-jwt")
    assert exc.value.status_code == 401


def test_decode_access_token_missing_sub():
    token = jwt.encode(
        {"aud": "authenticated", "exp": int(time.time()) + 3600},
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    with pytest.raises(HTTPException, match="subject"):
        decode_access_token(token)


def test_decode_access_token_user_metadata_email_fallback():
    token = _token(
        email=None,
        extra={"user_metadata": {"email": "meta@example.com"}},
    )
    user = decode_access_token(token)
    assert user.email == "meta@example.com"


def test_jwks_url_from_explicit_env(monkeypatch):
    from app import auth

    auth._jwk_client.cache_clear()
    monkeypatch.setenv("SUPABASE_JWT_JWKS_URL", "https://custom/jwks.json")
    assert auth._jwks_url() == "https://custom/jwks.json"


def test_jwks_url_requires_supabase_url(monkeypatch):
    from app import auth

    monkeypatch.delenv("SUPABASE_JWT_JWKS_URL", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        auth._jwks_url()
