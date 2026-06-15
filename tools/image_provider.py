"""Image generation providers for mangagen.

DirectOpenRouterProvider: uses OPENROUTER_API_KEY locally.
HostedMangaProvider: proxies through the manga hosted API with Supabase JWT.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Protocol

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


class ImageProvider(Protocol):
    def generate(
        self,
        messages_content,
        *,
        model: str,
        max_tokens: int,
        timeout: int = 300,
        retries: int = 2,
        image_config: dict | None = None,
    ) -> dict: ...


def openrouter_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER")
    if not key:
        sys.exit("OPENROUTER_API_KEY (or OPENROUTER) is required.")
    return key


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    *,
    timeout: int,
    retries: int,
) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last: Exception | None = None
    for attempt in range(1, retries + 2):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError):
                body = exc.read().decode("utf-8", "replace")[:1500]
                last = RuntimeError(f"HTTP {exc.code}: {body}")
            if attempt <= retries:
                time.sleep(min(30, 2 ** attempt))
    assert last is not None
    raise last


def build_openrouter_payload(
    messages_content,
    *,
    model: str,
    max_tokens: int,
    image_config: dict | None = None,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": messages_content}],
        "stream": False,
        "max_tokens": max_tokens,
    }
    if image_config is not None:
        payload["modalities"] = ["image", "text"]
        payload["image_config"] = image_config
    return payload


def _post_generate(
    url: str,
    headers: dict[str, str],
    messages_content,
    *,
    model: str,
    max_tokens: int,
    timeout: int,
    retries: int,
    image_config: dict | None,
) -> dict:
    payload = build_openrouter_payload(
        messages_content,
        model=model,
        max_tokens=max_tokens,
        image_config=image_config,
    )
    return _http_post_json(url, payload, headers, timeout=timeout, retries=retries)


class DirectOpenRouterProvider:
    def generate(
        self,
        messages_content,
        *,
        model: str,
        max_tokens: int,
        timeout: int = 300,
        retries: int = 2,
        image_config: dict | None = None,
    ) -> dict:
        return _post_generate(
            os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
            {
                "Authorization": f"Bearer {openrouter_api_key()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://local.mangagen",
                "X-Title": "mangagen",
            },
            messages_content,
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
            image_config=image_config,
        )


class HostedMangaProvider:
    def __init__(self, *, api_url: str, access_token: str):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token

    def generate(
        self,
        messages_content,
        *,
        model: str,
        max_tokens: int,
        timeout: int = 300,
        retries: int = 2,
        image_config: dict | None = None,
    ) -> dict:
        return _post_generate(
            f"{self.api_url}/v1/generate",
            {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            messages_content,
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
            image_config=image_config,
        )


_provider: ImageProvider | None = None


def get_provider() -> ImageProvider:
    global _provider
    if _provider is None:
        _provider = DirectOpenRouterProvider()
    return _provider


def set_provider(provider: ImageProvider | None) -> None:
    global _provider
    _provider = provider


def reset_provider() -> None:
    set_provider(None)
