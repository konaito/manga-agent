"""Local config and session paths for the manga CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from manga_hosted import is_prelaunch, load_hosted_defaults

_HOSTED = load_hosted_defaults()

CONFIG_DIR = Path(os.environ.get("MANGA_CONFIG_DIR", Path.home() / ".config" / "manga"))
SESSION_PATH = CONFIG_DIR / "session.json"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CALLBACK_PORT = 17489
DEFAULT_API_URL = _HOSTED["api_url"]


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(data: dict) -> None:
    ensure_config_dir()
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_session() -> dict | None:
    if not SESSION_PATH.exists():
        return None
    return json.loads(SESSION_PATH.read_text(encoding="utf-8"))


def save_session(data: dict) -> None:
    ensure_config_dir()
    SESSION_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SESSION_PATH.chmod(0o600)


def clear_session() -> None:
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()


def supabase_url() -> str:
    url = os.environ.get("MANGA_SUPABASE_URL") or load_config().get("supabase_url") or _HOSTED.get("supabase_url")
    if not url:
        raise SystemExit(
            "MANGA_SUPABASE_URL is not set. Export it or add supabase_url to "
            f"{CONFIG_PATH} (or deploy manga_hosted.json)"
        )
    return url.rstrip("/")


def supabase_anon_key() -> str:
    key = os.environ.get("MANGA_SUPABASE_ANON_KEY") or load_config().get("supabase_anon_key") or _HOSTED.get("supabase_anon_key")
    if not key:
        raise SystemExit(
            "MANGA_SUPABASE_ANON_KEY is not set. Export it or add supabase_anon_key to "
            f"{CONFIG_PATH} (or deploy manga_hosted.json)"
        )
    return key


def normalize_api_url(url: str) -> str:
    value = url.strip().rstrip("/")
    if not value.startswith("https://"):
        raise SystemExit(f"API URL must start with https:// (got: {url!r})")
    return value


def resolve_login_api_url(explicit: str | None) -> str:
    if explicit:
        return normalize_api_url(explicit)
    if is_prelaunch():
        raise SystemExit(
            "Pre-launch: login requires an explicit hosted API URL.\n"
            "  manga login https://<hosted-api-url>"
        )
    return api_url()


def api_url() -> str:
    for candidate in (
        os.environ.get("MANGA_API_URL"),
        load_config().get("api_url"),
        None if is_prelaunch() else _HOSTED.get("api_url"),
        None if is_prelaunch() else DEFAULT_API_URL,
    ):
        if candidate:
            return str(candidate).rstrip("/")
    raise SystemExit(
        "No hosted API URL configured. Log in first:\n"
        "  manga login https://<hosted-api-url>"
    )


def callback_url(port: int = DEFAULT_CALLBACK_PORT, *, base: str | None = None) -> str:
    root = normalize_api_url(base) if base else api_url()
    return f"{root}/auth/cli-callback?port={port}"
