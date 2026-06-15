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
LOGIN_REQUIRED_MSG = "Session expired. Run: manga login <https://api-url>"
NOT_LOGGED_IN_MSG = "Not logged in. Run: manga login <https://api-url>"


def _config_value(config_key: str, env_var: str) -> str | None:
    return os.environ.get(env_var) or load_config().get(config_key) or _HOSTED.get(config_key)


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
    url = _config_value("supabase_url", "MANGA_SUPABASE_URL")
    if not url:
        raise SystemExit(
            "MANGA_SUPABASE_URL is not set. Export it or add supabase_url to "
            f"{CONFIG_PATH} (or deploy manga_hosted.json)"
        )
    return url.rstrip("/")


def supabase_anon_key() -> str:
    key = _config_value("supabase_anon_key", "MANGA_SUPABASE_ANON_KEY")
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
