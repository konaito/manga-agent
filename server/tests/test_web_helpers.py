"""Additional coverage tests for web helpers and image provider."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")

from app import web  # noqa: E402
from image_provider import get_provider, reset_provider  # noqa: E402


def test_supabase_env_helpers():
    assert web.supabase_url().startswith("https://")
    assert web.supabase_anon_key() == "anon-key"


def test_supabase_url_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        web.supabase_url()


def test_supabase_anon_key_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("MANGA_SUPABASE_ANON_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_ANON_KEY"):
        web.supabase_anon_key()


def test_get_provider_default():
    reset_provider()
    provider = get_provider()
    assert provider is not None
    reset_provider()
