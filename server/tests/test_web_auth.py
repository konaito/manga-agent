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


def test_humanize_auth_error_patterns():
    from app.web import humanize_auth_error

    assert "パスワード" in humanize_auth_error("Invalid login credentials")
    assert "既に登録" in humanize_auth_error("User already registered")
    assert "確認" in humanize_auth_error("Email not confirmed")
    assert "6文字" in humanize_auth_error("Password should be at least 6 characters")
    assert humanize_auth_error("other") == "other"


def test_signup_sets_cookie(client, monkeypatch):
    async def fake_sign_up(email: str, password: str) -> dict:
        return {
            "access_token": "signup-access",
            "refresh_token": "signup-refresh",
            "expires_in": 3600,
            "user": {"email": email},
        }

    monkeypatch.setattr("app.web._sign_up_with_password", fake_sign_up)
    resp = client.post(
        "/login",
        data={"email": "new@example.com", "password": "secret12", "mode": "signup"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert resp.cookies.get("manga_access_token") == "signup-access"


def test_home_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_dashboard_shows_balance(client, monkeypatch):
    import time

    import jwt

    token = jwt.encode(
        {
            "sub": "dash-user",
            "email": "dash@example.com",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )

    async def fake_balance(user_id: str) -> int:
        assert user_id == "dash-user"
        return 15

    monkeypatch.setattr("app.web.get_balance", fake_balance)
    resp = client.get("/dashboard", cookies={"manga_access_token": token})
    assert resp.status_code == 200
    assert "15" in resp.text
    assert "dash@example.com" in resp.text


def test_logout_clears_cookies(client):
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_login_page_signup_mode(client):
    resp = client.get("/login?mode=signup")
    assert resp.status_code == 200
    assert "アカウント作成" in resp.text


def test_signup_cli_redirect(client, monkeypatch):
    async def fake_sign_up(email: str, password: str) -> dict:
        return {
            "access_token": "signup-cli",
            "refresh_token": "refresh-cli",
            "expires_in": 3600,
        }

    monkeypatch.setattr("app.web._sign_up_with_password", fake_sign_up)
    resp = client.post(
        "/login",
        data={
            "email": "new@example.com",
            "password": "secret12",
            "mode": "signup",
            "cli_port": "17489",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "signup-cli" in resp.headers["location"]


def test_sign_up_normalizes_nested_session(monkeypatch):
    import asyncio

    from app.web import _sign_up_with_password

    async def fake_post(path, payload, *, error_status):  # noqa: ARG001
        return {
            "user": {"email": "nested@example.com"},
            "session": {
                "access_token": "nested-access",
                "refresh_token": "nested-refresh",
                "expires_in": 1800,
            },
        }

    monkeypatch.setattr("app.web._supabase_auth_post", fake_post)
    data = asyncio.run(_sign_up_with_password("nested@example.com", "secret12"))
    assert data["access_token"] == "nested-access"


def test_home_redirects_to_dashboard_when_logged_in(client):
    import time

    import jwt

    token = jwt.encode(
        {
            "sub": "home-user",
            "email": "home@example.com",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    resp = client.get("/", cookies={"manga_access_token": token}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


