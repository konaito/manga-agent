# Manga Hosted Provider

運営サーバー経由で画像生成するための認証・トークン・プロキシ構成です。ユーザーの CLI には OpenRouter API キーを置かず、Supabase 認証と manga token 残高で生成を制御します。

## 本番環境（imi-chat/manga）

| サービス | URL / ID |
|---|---|
| API + Web ログイン | https://manga-imi-chat.vercel.app |
| Supabase プロジェクト | `rcbwggvdesuyndfbbjjt`（imi-chat / manga） |
| Vercel プロジェクト | imi-chat/manga |

## 構成

| コンポーネント | 役割 |
|---|---|
| Web `/login` | ブラウザでメール+パスワードログイン / 新規登録 |
| Web `/dashboard` | ログイン後の manga token 残高表示 |
| `manga login` | ブラウザで `/login` を開き、認証後 localhost callback でセッション取得 |
| `manga token` | 残り manga token 数を表示 |
| `manga gen <spec.json> -page 1 2 4` | ホスト型プロバイダー経由で部分ページ生成 |
| `server/` | FastAPI（Vercel 上で稼働） |
| Supabase | 認証 + `user_tokens` / `token_ledger` |

## Web ログイン

1. `/login` を開く
2. メールアドレスとパスワードでログイン（新規は「新規登録はこちら」から）
3. `/dashboard` で残り token を確認（新規登録時は 50 付与）

## CLI（本番・プレローンチ）

[`tools/manga_hosted.json`](../tools/manga_hosted.json) の `"prelaunch": true` の間は、**ログイン時に API URL の明示が必須**です。

```bash
uv sync
uv run manga login https://<hosted-api-url>
# ブラウザでメール+パスワードを入力
uv run manga token
uv run manga gen examples/demo-product/manga/production/spec/storyboard.json -page 1 2
```

ログイン成功後は `~/.config/manga/config.json` に `api_url` が保存されるため、`token` / `gen` では URL の再指定は不要です。

本ローンチ時は `manga_hosted.json` の `"prelaunch": false` に切り替えると、`manga login` だけでもデフォルト URL が使われます。

## サーバー構成（FastAPI + Vercel）

```
server/
  app/
    main.py       # API + web ルーター統合
    web.py        # /login, /dashboard（メール+パスワード）
    auth.py       # Supabase JWKS JWT 検証
    tokens.py     # token 残高・減算
    proxy.py      # OpenRouter 転送
  main.py         # Vercel エントリポイント
  vercel.json
  requirements.txt
  supabase/
    config.toml
    migrations/001_user_tokens.sql
```

### ローカル開発

```bash
cd server
uv sync --group server
export SUPABASE_URL=https://rcbwggvdesuyndfbbjjt.supabase.co
export SUPABASE_ANON_KEY=...
export SUPABASE_SERVICE_ROLE_KEY=...
export SUPABASE_JWT_JWKS_URL=https://rcbwggvdesuyndfbbjjt.supabase.co/auth/v1/.well-known/jwks.json
# HS256 プロジェクトでローカルJWT検証を使う場合のみ。未設定時は Supabase Auth /user で検証フォールバック
export SUPABASE_JWT_SECRET=...
export OPENROUTER_API_KEY=...
export MANGA_PUBLIC_URL=http://127.0.0.1:8000
uv run uvicorn app.main:app --reload --port 8000
```

### Vercel デプロイ

```bash
cd server
vercel link --project manga --scope imi-chat
vercel deploy --prod --scope imi-chat
```

環境変数（Vercel production）:

| 変数 | 用途 |
|---|---|
| `SUPABASE_URL` | Supabase プロジェクト URL |
| `SUPABASE_ANON_KEY` | Web ログイン用（password grant） |
| `SUPABASE_SERVICE_ROLE_KEY` | DB / RPC 操作 |
| `SUPABASE_JWT_JWKS_URL` | JWT 検証（JWKS型プロジェクト） |
| `SUPABASE_JWT_SECRET` | JWT 検証（HS256型プロジェクト、任意。未設定時は Supabase Auth `/user` にフォールバック） |
| `OPENROUTER_API_KEY` | 運営側 OpenRouter キー |
| `MANGA_PUBLIC_URL` | `https://manga-imi-chat.vercel.app` |
| `MANGA_COOKIE_SECURE` | `true` |

### Supabase 管理

```bash
cd server
npx supabase@latest link --project-ref rcbwggvdesuyndfbbjjt
npx supabase@latest config push --yes
npx supabase@latest db query --linked -f supabase/migrations/001_user_tokens.sql
```

初期 token は新規サインアップ時に **50** 自動付与（`signup_grant`）。追加付与:

```sql
select public.credit_manga_tokens(
  '<user-uuid>'::uuid,
  10,
  'welcome_grant'
);
```

## API

| Method | Path | 説明 |
|---|---|---|
| `GET` | `/health` | ヘルスチェック |
| `GET` | `/login` | Web ログインフォーム |
| `GET` | `/dashboard` | Web 残高ダッシュボード |
| `GET` | `/v1/me` | `{ user_id, email, manga_tokens }` |
| `POST` | `/v1/generate` | 画像生成（成功時 token -1） |

## セキュリティ

- OpenRouter API キーは Vercel 環境変数のみ
- CLI は `~/.config/manga/session.json` に Supabase セッションのみ保存
- JWT 検証は Supabase JWKS 経由（`SUPABASE_JWT_JWKS_URL`）
