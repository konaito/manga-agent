#!/usr/bin/env python3
"""manga CLI — login, token balance, and hosted image generation."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

# Allow running from repo without install.
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import mangagen  # noqa: E402
from image_provider import DirectOpenRouterProvider, HostedMangaProvider, reset_provider, set_provider  # noqa: E402
from manga_config import (  # noqa: E402
    DEFAULT_CALLBACK_PORT,
    api_url,
    clear_session,
    load_config,
    load_session,
    resolve_login_api_url,
    save_config,
    save_session,
    supabase_anon_key,
    supabase_url,
)


class LoginCallbackError(Exception):
    pass


def _supabase_headers() -> dict[str, str]:
    anon = supabase_anon_key()
    return {
        "apikey": anon,
        "Authorization": f"Bearer {anon}",
        "Content-Type": "application/json",
    }


def refresh_session(session: dict) -> dict:
    refresh = session.get("refresh_token")
    if not refresh:
        raise SystemExit("Session expired. Run: manga login <https://api-url>")

    token_url = f"{supabase_url()}/auth/v1/token?grant_type=refresh_token"
    with httpx.Client(timeout=30) as client:
        resp = client.post(token_url, headers=_supabase_headers(), json={"refresh_token": refresh})
    if resp.status_code >= 400:
        clear_session()
        raise SystemExit("Session expired. Run: manga login <https://api-url>")
    data = resp.json()
    updated = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh),
        "expires_at": int(time.time()) + int(data.get("expires_in", 3600)),
        "email": session.get("email"),
    }
    save_session(updated)
    return updated


def get_access_token() -> str | None:
    session = load_session()
    if not session:
        return None
    expires_at = session.get("expires_at", 0)
    if expires_at and time.time() >= expires_at - 60:
        session = refresh_session(session)
    return session.get("access_token")


def parse_callback_tokens(path: str, query: str, fragment: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in (query, fragment):
        if part.startswith("?"):
            part = part[1:]
        if not part:
            continue
        parsed = urllib.parse.parse_qs(part, keep_blank_values=True)
        for key, values in parsed.items():
            if values:
                params[key] = values[0]
    if path.endswith("/error") or params.get("error"):
        raise LoginCallbackError(params.get("error_description") or params.get("error") or "login failed")
    if not params.get("access_token"):
        raise LoginCallbackError("missing access_token in callback")
    return params


def wait_for_callback(port: int = DEFAULT_CALLBACK_PORT, *, timeout: int = 300) -> dict[str, str]:
    result: dict[str, str] | None = None
    error: Exception | None = None
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: ARG002
            return

        def do_GET(self):  # noqa: N802
            nonlocal result, error
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/callback/done":
                try:
                    result = parse_callback_tokens(parsed.path, parsed.query, "")
                except LoginCallbackError as exc:
                    error = exc
                except Exception as exc:  # noqa: BLE001
                    error = exc
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                if error:
                    body = "<h1>Login failed</h1><p>You can close this tab.</p>"
                else:
                    body = "<h1>Login complete</h1><p>You can close this tab and return to the terminal.</p>"
                self.wfile.write(body.encode("utf-8"))
                done.set()
                return

            self.send_response(404)
            self.end_headers()

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if not done.wait(timeout):
        server.shutdown()
        raise SystemExit(f"Login timed out after {timeout}s. Complete sign-in in your browser.")
    server.shutdown()
    if error:
        raise SystemExit(f"Login failed: {error}")
    assert result is not None
    return result


def cmd_login(args: argparse.Namespace) -> None:
    base = resolve_login_api_url(args.api_url)
    cfg = load_config()
    cfg["api_url"] = base
    save_config(cfg)

    login_url = f"{base}/login?cli_port={args.port}"
    print(f"Open in your browser and sign in:\n  {login_url}")
    print(f"Waiting for callback on 127.0.0.1:{args.port} ...")
    webbrowser.open(login_url)

    tokens = wait_for_callback(args.port, timeout=args.timeout)
    expires_in = int(tokens.get("expires_in", "3600"))
    email = ""
    session = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": int(time.time()) + expires_in,
        "email": email,
    }
    save_session(session)
    print("Logged in successfully.")


def cmd_logout(_args: argparse.Namespace) -> None:
    clear_session()
    print("Logged out.")


def cmd_token(_args: argparse.Namespace) -> None:
    token = get_access_token()
    if not token:
        raise SystemExit("Not logged in. Run: manga login <https://api-url>")

    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{api_url()}/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code == 401:
        clear_session()
        raise SystemExit("Session expired. Run: manga login <https://api-url>")
    if resp.status_code >= 400:
        raise SystemExit(f"Failed to fetch balance: {resp.status_code} {resp.text[:500]}")

    data = resp.json()
    print(data["manga_tokens"])


def parse_page_list(values: list[str]) -> str:
    if not values:
        raise SystemExit("manga gen requires -page with at least one page number")
    pages: list[int] = []
    for item in values:
        if "-" in item:
            lo, hi = item.split("-", 1)
            pages.extend(range(int(lo), int(hi) + 1))
        else:
            pages.append(int(item))
    return ",".join(str(p) for p in sorted(set(pages)))


def resolve_provider():
    access = get_access_token()
    if access:
        return HostedMangaProvider(api_url=api_url(), access_token=access)

    if os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER"):
        return DirectOpenRouterProvider()

    raise SystemExit("Not logged in and no OPENROUTER_API_KEY. Run: manga login <https://api-url>")


def cmd_gen(args: argparse.Namespace) -> None:
    spec = Path(args.spec).resolve()
    if not spec.exists():
        raise SystemExit(f"Spec not found: {spec}")

    provider = resolve_provider()
    set_provider(provider)
    try:
        project = mangagen.Project(spec)
        gen_args = argparse.Namespace(
            pages=parse_page_list(args.page),
            all_pages=False,
            model=os.environ.get("OPENROUTER_MODEL", mangagen.DEFAULT_GEN_MODEL),
            image_size=os.environ.get("OPENROUTER_IMAGE_SIZE", "1K"),
            max_tokens=int(os.environ.get("OPENROUTER_MAX_TOKENS", mangagen.DEFAULT_MAX_TOKENS)),
            concurrency=args.concurrency,
            candidates=1,
            force=args.force,
        )
        mangagen.cmd_gen(project, gen_args)
    finally:
        reset_provider()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manga", description="Manga hosted provider CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Sign in via browser (email + password)")
    login.add_argument(
        "api_url",
        nargs="?",
        help="Hosted API base URL (required before launch, e.g. https://<hosted-api-url>)",
    )
    login.add_argument("--port", type=int, default=DEFAULT_CALLBACK_PORT)
    login.add_argument("--timeout", type=int, default=300)
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser("logout", help="Clear local session")
    logout.set_defaults(func=cmd_logout)

    token = sub.add_parser("token", help="Show remaining manga tokens")
    token.set_defaults(func=cmd_token)

    gen = sub.add_parser("gen", help="Generate manga pages via hosted or direct provider")
    gen.add_argument("spec", help="Path to storyboard.json")
    gen.add_argument("-page", nargs="+", dest="page", metavar="N", help="Page numbers (e.g. -page 1 2 4)")
    gen.add_argument("--concurrency", type=int, default=4)
    gen.add_argument("--force", action="store_true", help="Proceed despite lint errors")
    gen.set_defaults(func=cmd_gen)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
