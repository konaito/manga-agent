"""Tests for image generation providers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from image_provider import (  # noqa: E402
    DirectOpenRouterProvider,
    HostedMangaProvider,
    _http_post_json,
    build_openrouter_payload,
    openrouter_api_key,
    reset_provider,
    set_provider,
)


def test_build_openrouter_payload_includes_image_config():
    payload = build_openrouter_payload(
        "prompt",
        model="test-model",
        max_tokens=1000,
        image_config={"aspect_ratio": "2:3"},
    )
    assert payload["model"] == "test-model"
    assert payload["modalities"] == ["image", "text"]
    assert payload["image_config"]["aspect_ratio"] == "2:3"


def test_build_openrouter_payload_without_image_config():
    payload = build_openrouter_payload("prompt", model="m", max_tokens=10)
    assert "modalities" not in payload


def test_hosted_provider_posts_to_manga_api():
    provider = HostedMangaProvider(api_url="https://api.manga.test", access_token="jwt-token")
    response = {"choices": [{"message": {"images": []}}]}

    with patch("image_provider._http_post_json", return_value=response) as mock_post:
        result = provider.generate(
            "hello",
            model="openai/gpt-5.4-image-2",
            max_tokens=16384,
            image_config={"aspect_ratio": "2:3", "image_size": "1K"},
        )

    assert result == response
    url, payload, headers = mock_post.call_args[0]
    assert url == "https://api.manga.test/v1/generate"
    assert headers["Authorization"] == "Bearer jwt-token"
    assert payload["model"] == "openai/gpt-5.4-image-2"


def test_direct_provider_posts_to_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    provider = DirectOpenRouterProvider()
    response = {"choices": []}

    with patch("image_provider._http_post_json", return_value=response) as mock_post:
        provider.generate("hello", model="m", max_tokens=100)

    url, _payload, headers = mock_post.call_args[0]
    assert "openrouter.ai" in url
    assert headers["Authorization"] == "Bearer or-key"
    assert headers["X-Title"] == "mangagen"


def test_hosted_provider_surfaces_402_message():
    provider = HostedMangaProvider(api_url="https://api.manga.test", access_token="jwt-token")

    with patch(
        "image_provider._http_post_json",
        side_effect=RuntimeError("HTTP 402: Insufficient manga tokens"),
    ):
        with pytest.raises(RuntimeError, match="402"):
            provider.generate("hello", model="m", max_tokens=100)


def test_openrouter_api_key_exits_when_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER", raising=False)
    with pytest.raises(SystemExit, match="OPENROUTER"):
        openrouter_api_key()


def test_openrouter_api_key_accepts_openrouter_alias(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER", "alias-key")
    assert openrouter_api_key() == "alias-key"


def test_http_post_json_retries_then_succeeds():
    calls = {"n": 0}
    payload = {"ok": True}

    class FakeResp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            import urllib.error

            raise urllib.error.URLError("temporary")
        return FakeResp()

    with patch("image_provider.time.sleep"), patch("image_provider.urllib.request.urlopen", fake_urlopen):
        result = _http_post_json("https://example.test", {"a": 1}, {}, timeout=1, retries=1)
    assert result == payload
    assert calls["n"] == 2


def test_http_post_json_raises_http_error_body():
    import urllib.error

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        raise urllib.error.HTTPError("https://x", 500, "err", {}, None)

    with patch("image_provider.time.sleep"), patch("image_provider.urllib.request.urlopen", fake_urlopen):
        with pytest.raises(RuntimeError, match="HTTP 500"):
            _http_post_json("https://example.test", {}, {}, timeout=1, retries=0)


def test_set_provider_injection():
    mock = MagicMock()
    mock.generate.return_value = {"ok": True}
    set_provider(mock)
    try:
        from mangagen import call_api

        result = call_api("x", model="m", max_tokens=10)
        assert result == {"ok": True}
        mock.generate.assert_called_once()
    finally:
        reset_provider()
