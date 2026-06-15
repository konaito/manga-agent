"""Public defaults for imi-chat/manga hosted provider (no secrets)."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULTS_PATH = Path(__file__).resolve().parent / "manga_hosted.json"

_FALLBACK = {
    "prelaunch": True,
    "api_url": "https://manga-imi-chat.vercel.app",
    "supabase_url": "",
    "supabase_anon_key": "",
}


def load_hosted_defaults() -> dict:
    if not DEFAULTS_PATH.exists():
        return dict(_FALLBACK)
    data = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    merged = {**_FALLBACK, **data}
    return merged


def is_prelaunch() -> bool:
    return bool(load_hosted_defaults().get("prelaunch", True))
