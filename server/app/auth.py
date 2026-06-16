"""Supabase JWT validation for the manga hosted provider API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str | None


def _jwks_url() -> str:
    explicit = os.environ.get("SUPABASE_JWT_JWKS_URL")
    if explicit:
        return explicit
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SUPABASE_URL or SUPABASE_JWT_JWKS_URL is required")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is required")
    return url


def _supabase_anon_key() -> str:
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("MANGA_SUPABASE_ANON_KEY")
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is required")
    return key


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    return PyJWKClient(_jwks_url())


def decode_access_token(token: str) -> AuthUser:
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "HS256"],
            audience="authenticated",
            options={"verify_aud": True},
        )
    except jwt.PyJWTError as exc:
        # Legacy projects may still use HS256 with shared secret.
        secret = os.environ.get("SUPABASE_JWT_SECRET")
        if not secret:
            raise HTTPException(status_code=401, detail="Invalid access token") from exc
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.PyJWTError as inner:
            raise HTTPException(status_code=401, detail="Invalid access token") from inner

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing subject in token")

    email = payload.get("email")
    if not email and isinstance(payload.get("user_metadata"), dict):
        email = payload["user_metadata"].get("email")

    return AuthUser(user_id=user_id, email=email)


async def _auth_user_from_supabase(token: str) -> AuthUser:
    headers = {
        "apikey": _supabase_anon_key(),
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{_supabase_url()}/auth/v1/user", headers=headers)
    if resp.status_code >= 400:
        raise HTTPException(status_code=401, detail="Invalid access token")

    data = resp.json()
    user_id = data.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing subject in token")
    return AuthUser(user_id=user_id, email=data.get("email"))


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        return decode_access_token(credentials.credentials)
    except HTTPException as exc:
        try:
            return await _auth_user_from_supabase(credentials.credentials)
        except (HTTPException, RuntimeError) as fallback_exc:
            if isinstance(fallback_exc, HTTPException):
                raise fallback_exc from exc
            raise exc
