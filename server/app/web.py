"""Web login pages and session handling for the manga hosted provider."""

from __future__ import annotations

import os
from html import escape
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import AuthUser, decode_access_token
from app.tokens import get_balance

router = APIRouter(tags=["web"])

ACCESS_COOKIE = "manga_access_token"
REFRESH_COOKIE = "manga_refresh_token"
EMAIL_COOKIE = "manga_email"


def supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is required")
    return url


def supabase_anon_key() -> str:
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("MANGA_SUPABASE_ANON_KEY")
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is required")
    return key


def _supabase_headers() -> dict[str, str]:
    anon = supabase_anon_key()
    return {
        "apikey": anon,
        "Authorization": f"Bearer {anon}",
        "Content-Type": "application/json",
    }


def humanize_auth_error(message: str) -> str:
    lower = message.lower()
    if "invalid login credentials" in lower:
        return "メールアドレスまたはパスワードが違います。"
    if "already registered" in lower or "already been registered" in lower:
        return "このメールアドレスは既に登録されています。ログインしてください。"
    if "email not confirmed" in lower:
        return "メールアドレスの確認が完了していません。"
    if "password should be at least" in lower:
        return "パスワードは6文字以上にしてください。"
    return message


def _layout(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} — Manga</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0f1115;
      --card: #171a21;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --accent: #f97316;
      --border: #2a2f3a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
      background: radial-gradient(circle at top, #1f2937 0%, var(--bg) 55%);
      color: var(--text);
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      width: min(100%, 420px);
      background: color-mix(in srgb, var(--card) 92%, white 8%);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 28px;
      box-shadow: 0 24px 80px rgba(0,0,0,.35);
    }}
    h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
    p {{ margin: 0 0 16px; color: var(--muted); line-height: 1.6; }}
    label {{ display: block; margin-bottom: 8px; font-size: .9rem; }}
    input[type=email], input[type=password] {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #0b0d11;
      color: var(--text);
      margin-bottom: 16px;
    }}
    button, .btn {{
      display: inline-block;
      width: 100%;
      padding: 12px 14px;
      border: 0;
      border-radius: 10px;
      background: var(--accent);
      color: #111;
      font-weight: 700;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
    }}
    .metric {{
      font-size: 3rem;
      font-weight: 800;
      margin: 12px 0 4px;
    }}
    .error {{ color: #fca5a5; margin-bottom: 12px; }}
    .links {{ margin-top: 18px; display: grid; gap: 10px; }}
    .links a {{ color: var(--muted); font-size: .9rem; }}
    .mode-toggle {{ margin-top: 12px; text-align: center; }}
    .mode-toggle a {{ color: var(--accent); text-decoration: none; font-size: .9rem; }}
  </style>
</head>
<body>
  <main class="card">{body}</main>
</body>
</html>"""


def _user_from_request(request: Request) -> AuthUser | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        return decode_access_token(token)
    except HTTPException:
        return None


def _auth_error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:300]
    return str(data.get("error_description") or data.get("msg") or resp.text[:300])


async def _supabase_auth_post(path: str, payload: dict, *, error_status: int) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{supabase_url()}{path}",
            headers=_supabase_headers(),
            json=payload,
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=error_status, detail=humanize_auth_error(_auth_error_detail(resp)))
    return resp.json()


async def _sign_in_with_password(email: str, password: str) -> dict:
    return await _supabase_auth_post(
        "/auth/v1/token?grant_type=password",
        {"email": email, "password": password},
        error_status=401,
    )


async def _sign_up_with_password(email: str, password: str) -> dict:
    data = await _supabase_auth_post(
        "/auth/v1/signup",
        {"email": email, "password": password},
        error_status=400,
    )
    if data.get("access_token"):
        return data
    session = data.get("session") or {}
    if session.get("access_token"):
        return {
            "access_token": session["access_token"],
            "refresh_token": session.get("refresh_token", ""),
            "expires_in": session.get("expires_in", 3600),
            "user": data.get("user"),
        }
    raise HTTPException(status_code=400, detail="アカウント作成に失敗しました。")


def _set_session_cookies(response: Response, *, access_token: str, refresh_token: str, email: str) -> None:
    secure = os.environ.get("VERCEL") == "1" or os.environ.get("MANGA_COOKIE_SECURE", "").lower() == "true"
    common = {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": 60 * 60 * 24 * 30,
        "path": "/",
    }
    response.set_cookie(ACCESS_COOKIE, access_token, **common)
    if refresh_token:
        response.set_cookie(REFRESH_COOKIE, refresh_token, **common)
    response.set_cookie(EMAIL_COOKIE, email, **{**common, "httponly": False})


def _session_from_auth(data: dict, *, email: str) -> tuple[str, str, str]:
    access = data.get("access_token", "")
    refresh = data.get("refresh_token", "")
    resolved_email = email
    user = data.get("user") or {}
    if isinstance(user, dict) and user.get("email"):
        resolved_email = user["email"]
    if not access:
        raise HTTPException(status_code=502, detail="認証トークンを取得できませんでした。")
    return access, refresh, resolved_email


def _cli_redirect(port: str, *, access_token: str, refresh_token: str, expires_in: int) -> RedirectResponse:
    safe_port = port if port.isdigit() else "17489"
    query = urlencode({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": str(expires_in),
        "token_type": "bearer",
    })
    return RedirectResponse(f"http://127.0.0.1:{safe_port}/callback/done?{query}", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if _user_from_request(request):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: str = "",
    mode: str = "signin",
    cli_port: str = "",
):
    if _user_from_request(request) and not cli_port:
        return RedirectResponse("/dashboard", status_code=302)

    signin = mode != "signup"
    title = "ログイン" if signin else "新規登録"
    intro = "メールアドレスとパスワードでログインします。" if signin else "アカウントを作成します（初回 50 manga token 付与）。"
    if cli_port.isdigit():
        intro += " 認証後、ターミナルへ戻ります。"

    submit_label = "ログイン" if signin else "アカウント作成"
    toggle_mode = "signup" if signin else "signin"
    toggle_label = "新規登録はこちら" if signin else "ログインはこちら"

    cli_q = f"&cli_port={escape(cli_port)}" if cli_port.isdigit() else ""
    body = f"<h1>Manga に{title}</h1><p>{intro}</p>"
    if error:
        body += f'<p class="error">{escape(error)}</p>'
    body += f"""
<form method="post" action="/login">
  <input type="hidden" name="mode" value="{'signin' if signin else 'signup'}">
  <input type="hidden" name="cli_port" value="{escape(cli_port)}">
  <label for="email">メールアドレス</label>
  <input id="email" name="email" type="email" required autocomplete="email" placeholder="you@example.com">
  <label for="password">パスワード</label>
  <input id="password" name="password" type="password" required autocomplete="{'current-password' if signin else 'new-password'}" minlength="6">
  <button type="submit">{submit_label}</button>
</form>
<p class="mode-toggle"><a href="/login?mode={toggle_mode}{cli_q}">{toggle_label}</a></p>
<div class="links"><a href="/health">API status</a></div>
"""
    return HTMLResponse(_layout(title, body))


@router.post("/login")
async def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    mode: str = Form(default="signin"),
    cli_port: str = Form(default=""),
):
    email = email.strip()
    try:
        if mode == "signup":
            data = await _sign_up_with_password(email, password)
        else:
            data = await _sign_in_with_password(email, password)
    except HTTPException as exc:
        query = urlencode({
            "error": str(exc.detail),
            "mode": mode,
            **({"cli_port": cli_port} if cli_port.isdigit() else {}),
        })
        return RedirectResponse(f"/login?{query}", status_code=303)

    access, refresh, resolved_email = _session_from_auth(data, email=email)
    expires_in = int(data.get("expires_in", 3600))

    if cli_port.isdigit():
        return _cli_redirect(cli_port, access_token=access, refresh_token=refresh, expires_in=expires_in)

    response = RedirectResponse("/dashboard", status_code=303)
    _set_session_cookies(response, access_token=access, refresh_token=refresh, email=resolved_email)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _user_from_request(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    balance = await get_balance(user.user_id)
    email = escape(user.email or request.cookies.get(EMAIL_COOKIE) or "")
    body = f"""
<h1>ダッシュボード</h1>
<p>{email}</p>
<p>残り manga token</p>
<div class="metric">{balance}</div>
<p>CLI では <code>manga token</code> / <code>manga gen spec.json -page 1</code> が使えます。</p>
<div class="links">
  <form method="post" action="/logout"><button type="submit">ログアウト</button></form>
</div>
"""
    return HTMLResponse(_layout("ダッシュボード", body))


@router.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, EMAIL_COOKIE):
        response.delete_cookie(name, path="/")
    return response
