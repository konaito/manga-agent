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


@pytest.mark.asyncio
async def test_require_user_falls_back_to_supabase_user(monkeypatch):
    from app import auth

    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    def fail_decode(_token: str) -> AuthUser:
        raise HTTPException(status_code=401, detail="Invalid access token")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "supabase-user", "email": "fallback@example.com"}

    async def fake_get(url, headers=None):  # noqa: ARG001
        assert url == "https://example.supabase.co/auth/v1/user"
        assert headers["apikey"] == "anon-key"
        assert headers["Authorization"] == "Bearer remote-token"
        return FakeResponse()

    monkeypatch.setattr(auth, "decode_access_token", fail_decode)
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="remote-token")
    user = await require_user(creds)
    assert user == AuthUser(user_id="supabase-user", email="fallback@example.com")


def test_decode_access_token_invalid():
    with pytest.raises(HTTPException) as exc:
        decode_access_token("not-a-jwt")
    assert exc.value.status_code == 401


def test_decode_access_token_invalid_without_secret(monkeypatch):
    from app import auth

    auth._jwk_client.cache_clear()
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
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


def test_supabase_auth_env_helpers_require_env(monkeypatch):
    from app import auth

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        auth._supabase_url()

    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("MANGA_SUPABASE_ANON_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_ANON_KEY"):
        auth._supabase_anon_key()


@pytest.mark.asyncio
async def test_auth_user_from_supabase_rejects_remote_401(monkeypatch):
    from app import auth

    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    class FakeResponse:
        status_code = 401

        def json(self):
            return {}

    async def fake_get(url, headers=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))
    with pytest.raises(HTTPException) as exc:
        await auth._auth_user_from_supabase("bad-token")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_user_from_supabase_requires_user_id(monkeypatch):
    from app import auth

    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"email": "missing-id@example.com"}

    async def fake_get(url, headers=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))
    with pytest.raises(HTTPException, match="subject"):
        await auth._auth_user_from_supabase("bad-token")


@pytest.mark.asyncio
async def test_require_user_raises_supabase_fallback_error(monkeypatch):
    from app import auth

    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda _token: (_ for _ in ()).throw(HTTPException(status_code=401, detail="local failed")),
    )

    class FakeResponse:
        status_code = 401

        def json(self):
            return {}

    async def fake_get(url, headers=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
    with pytest.raises(HTTPException) as exc:
        await require_user(creds)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_keeps_original_error_when_fallback_unconfigured(monkeypatch):
    from app import auth

    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("MANGA_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda _token: (_ for _ in ()).throw(HTTPException(status_code=401, detail="local failed")),
    )

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
    with pytest.raises(HTTPException) as exc:
        await require_user(creds)
    assert exc.value.detail == "local failed"


class _AsyncCtx:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        return await self.handler(*args, **kwargs)
