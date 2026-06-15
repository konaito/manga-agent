"""Tests for the manga CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from manga_cli import parse_callback_tokens, parse_page_list  # noqa: E402
from manga_config import normalize_api_url, resolve_login_api_url  # noqa: E402
from manga_hosted import load_hosted_defaults  # noqa: E402


def test_parse_page_list_space_separated():
    assert parse_page_list(["1", "2", "4"]) == "1,2,4"


def test_parse_page_list_range():
    assert parse_page_list(["1", "3-5"]) == "1,3,4,5"


def test_parse_page_list_requires_values():
    with pytest.raises(SystemExit):
        parse_page_list([])


def test_parse_callback_tokens_from_query():
    tokens = parse_callback_tokens(
        "/callback/done",
        "access_token=abc&refresh_token=def&expires_in=3600",
        "",
    )
    assert tokens["access_token"] == "abc"
    assert tokens["refresh_token"] == "def"


def test_parse_callback_tokens_error():
    with pytest.raises(Exception, match="denied"):
        parse_callback_tokens("/callback/done", "error=access_denied&error_description=denied", "")


def test_normalize_api_url_requires_https():
    assert normalize_api_url("https://manga-imi-chat.vercel.app/") == "https://manga-imi-chat.vercel.app"
    with pytest.raises(SystemExit):
        normalize_api_url("http://localhost:8000")


def test_resolve_login_api_url_requires_explicit_in_prelaunch(monkeypatch):
    monkeypatch.setattr(
        "manga_config.load_hosted_defaults",
        lambda: {**load_hosted_defaults(), "prelaunch": True},
    )
    with pytest.raises(SystemExit, match="Pre-launch"):
        resolve_login_api_url(None)
    assert (
        resolve_login_api_url("https://manga-imi-chat.vercel.app")
        == "https://manga-imi-chat.vercel.app"
    )
