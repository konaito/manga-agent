"""Tests for OpenRouter proxy."""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("OPENROUTER_API_KEY", "or-test-key")

from app.proxy import forward_generate  # noqa: E402


@pytest.mark.asyncio
async def test_forward_generate_success(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"images": []}}]}

    async def fake_post(url, headers=None, json=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.proxy.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_post))
    result = await forward_generate({"model": "m", "messages": []})
    assert "choices" in result


@pytest.mark.asyncio
async def test_forward_generate_upstream_error(monkeypatch):
    class FakeResponse:
        status_code = 502
        text = "upstream failed"

    async def fake_post(url, headers=None, json=None):  # noqa: ARG001
        return FakeResponse()

    monkeypatch.setattr("app.proxy.httpx.AsyncClient", lambda *a, **k: _AsyncCtx(fake_post))
    with pytest.raises(HTTPException) as exc:
        await forward_generate({"model": "m"})
    assert exc.value.status_code == 502


def test_openrouter_key_missing(monkeypatch):
    from app import proxy

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        proxy._openrouter_key()


class _AsyncCtx:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return await self.handler(*args, **kwargs)
