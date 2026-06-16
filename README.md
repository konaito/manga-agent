# Manga Agent

漫画の作り方を理解して、企画・キャラクター・ネーム・読み切り構成をレビューし、AI画像生成で漫画ページを制作するためのオープンソースツールキットです。

特定のLLMベンダーに依存しない「エージェント用プロンプトパック」＋「スペック駆動の制作ハーネス」で構成されています。

## クイックスタート

### 1. ネーム・企画のレビュー（LLM不要）

```bash
python3 tools/build_prompt.py --mode name-review path/to/draft.md
```

生成されたプロンプトを任意のLLMに貼り付けて使います。

### 2. ページ画像の生成

**A. 自分の OpenRouter API キーを使う（従来どおり）**

```bash
SPEC=examples/demo-product/manga/production/spec/storyboard.json

# 事前チェック（無料）
python3 tools/mangagen.py lint --spec $SPEC

# 編集レビュー依頼の生成（無料）
python3 tools/mangagen.py review --spec $SPEC

# プロンプト確認（無料）
python3 tools/mangagen.py prompts --spec $SPEC

# ページ生成（課金）
export OPENROUTER_API_KEY=your_key_here
python3 tools/mangagen.py gen --spec $SPEC --pages 1,2

# 画像QA依頼の生成（無料）
python3 tools/mangagen.py qa --spec $SPEC
```

**B. ホスト型プロバイダー（運営サーバー経由・ユーザー側 API キー不要）**

```bash
uv sync
uv tool install -e .

manga login https://<hosted-api-url>
manga token
manga gen examples/demo-product/manga/production/spec/storyboard.json -page 1 2
```

`uv tool install -e .` を実行すると、このリポジトリのCLIが編集可能インストールされ、`manga` コマンドを直接使えるようになります。

認証・トークン残高・サーバー構成の詳細は **[docs/hosted-provider.md](docs/hosted-provider.md)** を参照。

## リポジトリ構成

| パス | 役割 |
|---|---|
| `agents/manga_editor_agent.md` | 漫画編集者エージェントのシステムプロンプト |
| `tools/mangagen.py` | スペック駆動の制作ハーネス（lint / review / gen / qa / fix） |
| `tools/manga_cli.py` | ホスト型プロバイダー CLI（`manga login` / `token` / `gen`） |
| `tools/build_prompt.py` | レビュー依頼プロンプトを組み立てるCLI |
| `server/` | ホスト型プロバイダー API（FastAPI + Supabase + Vercel） |
| `docs/` | 漫画クラフト原則・ハーネス設計・制作知見 |
| `docs/hosted-provider.md` | ホスト型プロバイダーの認証・デプロイ手順 |
| `docs/knowledge/INDEX.md` | タスク着手前に読む知見の目次 |
| `templates/` | 企画入力・クラフトガイドのテンプレート |
| `examples/demo-product/` | ハーネス動作確認用のサンプルプロジェクト |
| `tests/` | mangagen のユニットテスト |

## エージェント向けドキュメント

AIエージェントがこのリポジトリを理解するための詳細ガイドは **[AGENTS.md](AGENTS.md)** を参照してください。

## 知見

タスク着手前に `docs/knowledge/INDEX.md` を見る。クラフト知見・ハーネス知見・制作ポストモーテムの目次。

## 開発

依存関係とテスト実行は `uv` を使います。

```bash
uv run pytest
```

## エージェントの基本方針

このエージェントは、ふわっと褒める相談相手ではなく、読者コストを下げながら漫画としての快感を増やす編集者として振る舞います。

特に見るもの:

- 1コマ内の情報量と、絵・セリフ・表情・吹き出しの一致
- 主人公が読者に好かれる理由と、その主人公にしかできない行動
- キャラ同士の関係性と、主人公へ向かう感情のベクトル
- 1ページ目と最終ページで何が変化するか
- 見せ場から逆算した構成になっているか
- 連載でアイデアが出続ける構造になっているか
- AI制作時に弱くなりやすい、表情・手の演技・位置関係・情報順序
- 読者が支払う時間と労力に見合うメリットがあるか

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照。
