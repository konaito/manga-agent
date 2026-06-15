"""Expanded tests for the manga CLI."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import manga_cli  # noqa: E402
import manga_config  # noqa: E402
from image_provider import DirectOpenRouterProvider, HostedMangaProvider  # noqa: E402
from manga_config import load_hosted_defaults  # noqa: E402
from conftest import book_spec  # noqa: E402


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MANGA_CONFIG_DIR", str(tmp_path))
    manga_config.CONFIG_DIR = tmp_path
    manga_config.CONFIG_PATH = tmp_path / "config.json"
    manga_config.SESSION_PATH = tmp_path / "session.json"
    return tmp_path


def test_parse_page_list_space_separated():
    assert manga_cli.parse_page_list(["1", "2", "4"]) == "1,2,4"


def test_parse_page_list_range():
    assert manga_cli.parse_page_list(["1", "3-5"]) == "1,3,4,5"


def test_parse_page_list_requires_values():
    with pytest.raises(SystemExit):
        manga_cli.parse_page_list([])


def test_parse_callback_tokens_from_query():
    tokens = manga_cli.parse_callback_tokens(
        "/callback/done",
        "access_token=abc&refresh_token=def&expires_in=3600",
        "",
    )
    assert tokens["access_token"] == "abc"
    assert tokens["refresh_token"] == "def"


def test_parse_callback_tokens_error():
    with pytest.raises(manga_cli.LoginCallbackError, match="denied"):
        manga_cli.parse_callback_tokens("/callback/done", "error=access_denied&error_description=denied", "")


def test_normalize_api_url_requires_https():
    assert manga_config.normalize_api_url("https://manga-imi-chat.vercel.app/") == "https://manga-imi-chat.vercel.app"
    with pytest.raises(SystemExit):
        manga_config.normalize_api_url("http://localhost:8000")


def test_resolve_login_api_url_requires_explicit_in_prelaunch(monkeypatch):
    monkeypatch.setattr(
        "manga_config.load_hosted_defaults",
        lambda: {**load_hosted_defaults(), "prelaunch": True},
    )
    with pytest.raises(SystemExit, match="Pre-launch"):
        manga_config.resolve_login_api_url(None)
    assert (
        manga_config.resolve_login_api_url("https://manga-imi-chat.vercel.app")
        == "https://manga-imi-chat.vercel.app"
    )


def test_refresh_session_updates_tokens(config_dir, monkeypatch):
    manga_config.save_session({"refresh_token": "r1", "email": "u@example.com", "expires_at": 0})

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"access_token": "new", "refresh_token": "r2", "expires_in": 7200}

    monkeypatch.setattr(manga_config, "supabase_url", lambda: "https://sb.test")
    monkeypatch.setattr(manga_config, "supabase_anon_key", lambda: "anon")
    with patch("manga_cli.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = FakeResponse()
        updated = manga_cli.refresh_session(manga_config.load_session())

    assert updated["access_token"] == "new"
    assert manga_config.load_session()["access_token"] == "new"


def test_refresh_session_clears_on_401(config_dir, monkeypatch):
    manga_config.save_session({"refresh_token": "r1", "expires_at": 0})

    class FakeResponse:
        status_code = 401

        def json(self):
            return {}

    monkeypatch.setattr(manga_config, "supabase_url", lambda: "https://sb.test")
    monkeypatch.setattr(manga_config, "supabase_anon_key", lambda: "anon")
    with patch("manga_cli.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = FakeResponse()
        with pytest.raises(SystemExit, match="Session expired"):
            manga_cli.refresh_session(manga_config.load_session())
    assert manga_config.load_session() is None


def test_get_access_token_refreshes_near_expiry(config_dir, monkeypatch):
    manga_config.save_session(
        {
            "access_token": "old",
            "refresh_token": "r1",
            "expires_at": int(time.time()) + 30,
            "email": "u@example.com",
        }
    )
    monkeypatch.setattr(manga_cli, "refresh_session", lambda s: {**s, "access_token": "fresh"})
    assert manga_cli.get_access_token() == "fresh"


def test_require_access_token_exits_when_missing():
    with patch("manga_cli.get_access_token", return_value=None):
        with pytest.raises(SystemExit, match="Not logged in"):
            manga_cli._require_access_token()


def test_refresh_session_requires_refresh_token(config_dir):
    manga_config.save_session({"expires_at": 0})
    with pytest.raises(SystemExit, match="Session expired"):
        manga_cli.refresh_session(manga_config.load_session())


def test_wait_for_callback_timeout():
    with pytest.raises(SystemExit, match="timed out"):
        manga_cli.wait_for_callback(38741, timeout=1)


def test_resolve_provider_hosted_when_logged_in(config_dir, monkeypatch):
    manga_config.save_session({"access_token": "jwt", "expires_at": int(time.time()) + 3600})
    manga_config.save_config({"api_url": "https://api.hosted.test"})
    provider = manga_cli.resolve_provider()
    assert isinstance(provider, HostedMangaProvider)


def test_resolve_provider_direct_when_openrouter_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER", raising=False)
    with patch("manga_cli.get_access_token", return_value=None):
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        provider = manga_cli.resolve_provider()
        assert isinstance(provider, DirectOpenRouterProvider)


def test_resolve_provider_exits_without_auth(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER", raising=False)
    with patch("manga_cli.get_access_token", return_value=None):
        with pytest.raises(SystemExit, match="Not logged in"):
            manga_cli.resolve_provider()


def test_cmd_logout_clears_session(config_dir, capsys):
    manga_config.save_session({"access_token": "x"})
    manga_cli.cmd_logout(argparse.Namespace())
    assert manga_config.load_session() is None
    assert "Logged out" in capsys.readouterr().out


def test_cmd_token_prints_balance(config_dir, capsys):
    manga_config.save_session({"access_token": "jwt", "expires_at": int(time.time()) + 3600})
    manga_config.save_config({"api_url": "https://api.hosted.test"})

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"manga_tokens": 42}

    with patch("manga_cli.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.return_value = FakeResponse()
        manga_cli.cmd_token(argparse.Namespace())
    assert capsys.readouterr().out.strip() == "42"


def test_session_from_callback_builds_expiry():
    session = manga_cli._session_from_callback(
        {"access_token": "a", "refresh_token": "r", "expires_in": "120"}
    )
    assert session["access_token"] == "a"
    assert session["expires_at"] > time.time()


def test_cmd_login_saves_session(config_dir, monkeypatch):
    monkeypatch.setattr(manga_cli, "resolve_login_api_url", lambda url: "https://api.hosted.test")
    monkeypatch.setattr(manga_cli, "webbrowser", MagicMock())
    monkeypatch.setattr(
        manga_cli,
        "wait_for_callback",
        lambda port, timeout=300: {"access_token": "tok", "refresh_token": "ref", "expires_in": "3600"},
    )
    args = argparse.Namespace(api_url="https://api.hosted.test", port=17489, timeout=300)
    manga_cli.cmd_login(args)
    assert manga_config.load_session()["access_token"] == "tok"


def test_cmd_gen_integration(tmp_path, monkeypatch):
    spec_dir = tmp_path / "production" / "spec"
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / "storyboard.json"
    spec_path.write_text(json.dumps(book_spec()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["manga", "gen", str(spec_path), "-page", "1", "--force"],
    )
    with patch("manga_cli.get_access_token", return_value=None):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        with patch("mangagen.cmd_gen", return_value=[]):
            assert manga_cli.main() == 0


def test_main_parser_logout(config_dir):
    with patch("sys.argv", ["manga", "logout"]):
        assert manga_cli.main() == 0
    assert manga_config.load_session() is None

