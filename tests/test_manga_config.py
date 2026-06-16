"""Tests for manga CLI config and session storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import manga_config  # noqa: E402


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MANGA_CONFIG_DIR", str(tmp_path))
    manga_config.CONFIG_DIR = tmp_path
    manga_config.CONFIG_PATH = tmp_path / "config.json"
    manga_config.SESSION_PATH = tmp_path / "session.json"
    return tmp_path


def test_save_and_load_config_round_trip(config_dir):
    manga_config.save_config({"api_url": "https://api.example.test"})
    assert manga_config.load_config()["api_url"] == "https://api.example.test"


def test_save_session_sets_permissions(config_dir):
    manga_config.save_session({"access_token": "abc"})
    assert manga_config.SESSION_PATH.exists()
    assert oct(manga_config.SESSION_PATH.stat().st_mode)[-3:] == "600"


def test_clear_session_removes_file(config_dir):
    manga_config.save_session({"access_token": "abc"})
    manga_config.clear_session()
    assert not manga_config.SESSION_PATH.exists()


def test_supabase_url_prefers_env(config_dir, monkeypatch):
    monkeypatch.setenv("MANGA_SUPABASE_URL", "https://env.supabase.co")
    assert manga_config.supabase_url() == "https://env.supabase.co"


def test_supabase_url_from_config(config_dir):
    manga_config.save_config({"supabase_url": "https://cfg.supabase.co/"})
    assert manga_config.supabase_url() == "https://cfg.supabase.co"


def test_supabase_url_missing_exits(config_dir, monkeypatch):
    monkeypatch.setattr(manga_config, "_HOSTED", {"supabase_url": ""})
    with pytest.raises(SystemExit, match="MANGA_SUPABASE_URL"):
        manga_config.supabase_url()


def test_supabase_anon_key_prefers_env(config_dir, monkeypatch):
    monkeypatch.setenv("MANGA_SUPABASE_ANON_KEY", "anon-env")
    assert manga_config.supabase_anon_key() == "anon-env"


def test_api_url_prefers_env(config_dir, monkeypatch):
    monkeypatch.setenv("MANGA_API_URL", "https://env-api.test/")
    assert manga_config.api_url() == "https://env-api.test"


def test_api_url_from_config(config_dir):
    manga_config.save_config({"api_url": "https://cfg-api.test"})
    assert manga_config.api_url() == "https://cfg-api.test"


def test_normalize_api_url_accepts_pasted_login_url():
    assert manga_config.normalize_api_url("https://api.example.test/login") == "https://api.example.test"
    assert (
        manga_config.normalize_api_url("https://api.example.test/login?cli_port=17489")
        == "https://api.example.test"
    )


def test_normalize_api_url_rejects_other_paths():
    with pytest.raises(SystemExit, match="hosted base URL"):
        manga_config.normalize_api_url("https://api.example.test/dashboard")


def test_api_url_missing_exits(config_dir, monkeypatch):
    monkeypatch.setattr(manga_config, "is_prelaunch", lambda: True)
    with pytest.raises(SystemExit, match="No hosted API URL"):
        manga_config.api_url()


def test_login_messages_are_stable():
    assert "login" in manga_config.LOGIN_REQUIRED_MSG.lower()
    assert "login" in manga_config.NOT_LOGGED_IN_MSG.lower()
