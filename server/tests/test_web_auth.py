"""Tests for web password authentication."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-unit-tests")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("OPENROUTER_API_KEY", "or-test-key")

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_login_page_has_password_field(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert 'type="password"' in resp.text
    assert "マジックリンク" not in resp.text


def test_login_page_cli_port_hint(client):
    resp = client.get("/login?cli_port=17489")
    assert resp.status_code == 200
    assert "ターミナルへ戻ります" in resp.text
    assert 'name="cli_port" value="17489"' in resp.text


def test_login_signin_sets_cookie(client, monkeypatch):
    async def fake_sign_in(email: str, password: str) -> dict:
        assert email == "user@example.com"
        assert password == "secret12"
        return {
            "access_token": "access-abc",
            "refresh_token": "refresh-abc",
            "expires_in": 3600,
            "user": {"email": "user@example.com"},
        }

    monkeypatch.setattr("app.web._sign_in_with_password", fake_sign_in)

    resp = client.post(
        "/login",
        data={"email": "user@example.com", "password": "secret12", "mode": "signin"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert resp.cookies.get("manga_access_token") == "access-abc"


def test_login_cli_redirect(client, monkeypatch):
    async def fake_sign_in(email: str, password: str) -> dict:
        return {
            "access_token": "access-cli",
            "refresh_token": "refresh-cli",
            "expires_in": 7200,
        }

    monkeypatch.setattr("app.web._sign_in_with_password", fake_sign_in)

    resp = client.post(
        "/login",
        data={
            "email": "user@example.com",
            "password": "secret12",
            "mode": "signin",
            "cli_port": "17489",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("http://127.0.0.1:17489/callback/done?")
    assert "access_token=access-cli" in location


def test_login_failure_redirects_with_error(client, monkeypatch):
    from fastapi import HTTPException

    async def fake_sign_in(email: str, password: str) -> dict:
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが違います。")

    monkeypatch.setattr("app.web._sign_in_with_password", fake_sign_in)

    resp = client.post(
        "/login",
        data={"email": "user@example.com", "password": "bad", "mode": "signin"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error=" in resp.headers["location"]
