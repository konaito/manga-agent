"""Tests for manga token balance operations."""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

from app import tokens  # noqa: E402


@pytest.mark.asyncio
async def test_get_balance_returns_zero_when_missing(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return []

    async def fake_get(url, headers=None, params=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))
    assert await tokens.get_balance("user-1") == 0


@pytest.mark.asyncio
async def test_get_balance_returns_value(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return [{"balance": 12}]

    async def fake_get(url, headers=None, params=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))
    assert await tokens.get_balance("user-1") == 12


@pytest.mark.asyncio
async def test_get_balance_supabase_error(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "db down"

    async def fake_get(url, headers=None, params=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_get))
    with pytest.raises(HTTPException) as exc:
        await tokens.get_balance("user-1")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_debit_token_success(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return 4

    async def fake_post(url, headers=None, json=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_post))
    assert await tokens.debit_token("user-1") == 4


@pytest.mark.asyncio
async def test_debit_token_insufficient(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return None

    async def fake_post(url, headers=None, json=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_post))
    with pytest.raises(HTTPException) as exc:
        await tokens.debit_token("user-1")
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_credit_token_success(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return 9

    async def fake_post(url, headers=None, json=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_post))
    assert await tokens.credit_token("user-1", amount=2, reason="refund") == 9


@pytest.mark.asyncio
async def test_credit_token_supabase_error(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "rpc failed"

    async def fake_post(url, headers=None, json=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.tokens.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_post))
    with pytest.raises(HTTPException) as exc:
        await tokens.credit_token("user-1")
    assert exc.value.status_code == 502


def test_service_key_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        tokens._service_key()


class _AsyncCtx:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        return await self.handler(*args, **kwargs)

    async def post(self, *args, **kwargs):
        return await self.handler(*args, **kwargs)
