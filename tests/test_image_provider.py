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
    build_openrouter_payload,
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


def test_hosted_provider_surfaces_402_message():
    provider = HostedMangaProvider(api_url="https://api.manga.test", access_token="jwt-token")

    with patch(
        "image_provider._http_post_json",
        side_effect=RuntimeError("HTTP 402: Insufficient manga tokens"),
    ):
        with pytest.raises(RuntimeError, match="402"):
            provider.generate("hello", model="m", max_tokens=100)


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
