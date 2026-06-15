"""Tests for hosted provider defaults."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import manga_hosted  # noqa: E402


def test_load_hosted_defaults_merges_file(tmp_path, monkeypatch):
    path = tmp_path / "manga_hosted.json"
    path.write_text(json.dumps({"prelaunch": False, "api_url": "https://custom.test"}), encoding="utf-8")
    monkeypatch.setattr(manga_hosted, "DEFAULTS_PATH", path)
    data = manga_hosted.load_hosted_defaults()
    assert data["prelaunch"] is False
    assert data["api_url"] == "https://custom.test"
    assert "supabase_url" in data


def test_load_hosted_defaults_fallback_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(manga_hosted, "DEFAULTS_PATH", tmp_path / "missing.json")
    data = manga_hosted.load_hosted_defaults()
    assert data["prelaunch"] is True
    assert data["api_url"].startswith("https://")


def test_is_prelaunch_reflects_defaults(monkeypatch):
    monkeypatch.setattr(manga_hosted, "load_hosted_defaults", lambda: {"prelaunch": True})
    assert manga_hosted.is_prelaunch() is True
    monkeypatch.setattr(manga_hosted, "load_hosted_defaults", lambda: {"prelaunch": False})
    assert manga_hosted.is_prelaunch() is False
