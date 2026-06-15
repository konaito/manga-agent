"""Tests for the manga hosted provider API."""

from __future__ import annotations

import os
import time

import jwt
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-unit-tests")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("OPENROUTER_API_KEY", "or-test-key")

from app.main import app  # noqa: E402


def _token(*, sub: str = "user-1", email: str = "user@example.com") -> str:
    payload = {
        "sub": sub,
        "email": email,
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_me_requires_auth(client):
    resp = client.get("/v1/me")
    assert resp.status_code == 401


def test_me_returns_balance(client, monkeypatch):
    async def fake_balance(user_id: str) -> int:
        assert user_id == "user-1"
        return 7

    monkeypatch.setattr("app.main.get_balance", fake_balance)
    resp = client.get("/v1/me", headers={"Authorization": f"Bearer {_token()}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["manga_tokens"] == 7
    assert data["email"] == "user@example.com"


def test_generate_insufficient_tokens(client, monkeypatch):
    async def fake_debit(user_id: str, *, reason: str = "generate") -> int:
        raise __import__("fastapi").HTTPException(status_code=402, detail="Insufficient manga tokens")

    monkeypatch.setattr("app.main.debit_token", fake_debit)
    payload = {
        "model": "openai/gpt-5.4-image-2",
        "messages": [{"role": "user", "content": "draw"}],
        "max_tokens": 100,
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": "2:3", "image_size": "1K"},
    }
    resp = client.post("/v1/generate", json=payload, headers={"Authorization": f"Bearer {_token()}"})
    assert resp.status_code == 402


def test_generate_success(client, monkeypatch):
    calls = {"debit": 0, "forward": 0}

    async def fake_debit(user_id: str, *, reason: str = "generate") -> int:
        calls["debit"] += 1
        return 4

    async def fake_forward(payload: dict) -> dict:
        calls["forward"] += 1
        return {
            "choices": [{
                "message": {
                    "images": [{"image_url": {"url": "data:image/png;base64,AAAA"}}],
                },
            }],
        }

    monkeypatch.setattr("app.main.debit_token", fake_debit)
    monkeypatch.setattr("app.main.forward_generate", fake_forward)

    payload = {
        "model": "openai/gpt-5.4-image-2",
        "messages": [{"role": "user", "content": "draw"}],
        "max_tokens": 100,
        "modalities": ["image", "text"],
    }
    resp = client.post("/v1/generate", json=payload, headers={"Authorization": f"Bearer {_token()}"})
    assert resp.status_code == 200
    assert calls["debit"] == 1
    assert calls["forward"] == 1


def test_generate_refunds_on_openrouter_failure(client, monkeypatch):
    refunds = []

    async def fake_debit(user_id: str, *, reason: str = "generate") -> int:
        return 2

    async def fake_forward(payload: dict) -> dict:
        raise __import__("fastapi").HTTPException(status_code=502, detail="upstream failed")

    async def fake_credit(user_id: str, *, amount: int = 1, reason: str = "refund") -> int:
        refunds.append((user_id, amount, reason))
        return 3

    monkeypatch.setattr("app.main.debit_token", fake_debit)
    monkeypatch.setattr("app.main.forward_generate", fake_forward)
    monkeypatch.setattr("app.main.credit_token", fake_credit)

    payload = {
        "model": "openai/gpt-5.4-image-2",
        "messages": [{"role": "user", "content": "draw"}],
        "max_tokens": 100,
    }
    resp = client.post("/v1/generate", json=payload, headers={"Authorization": f"Bearer {_token()}"})
    assert resp.status_code == 502
    assert refunds == [("user-1", 1, "generate_refund")]
