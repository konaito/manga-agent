# AGENTS.md — AIエージェント向けリポジトリガイド

このファイルは、AIエージェント（Cursor、Claude Code、Codex 等）がこのリポジトリを初めて見たときに読むためのガイドです。

## このリポジトリは何か

**Manga Agent** は2つの機能を持つオープンソースツールキットです。

1. **漫画編集者エージェント** — 企画・漫画脚本・ネーム・読み切り構成をレビューするためのプロンプトパック
2. **mangagen 制作ハーネス** — storyboard JSON を単一ソースとして、AI画像生成→エージェント画像QA依頼→フィードバック付き再生成まで行うCLI

特定のLLMベンダーに依存しません。OpenRouter APIは画像出力（ページ生成・キャラシート生成）にだけ使います。

## 最初に読むべきファイル

| 優先度 | ファイル | いつ読むか |
|---|---|---|
| 1 | `docs/knowledge/INDEX.md` | あらゆるタスクの着手前 |
| 2 | `agents/manga_editor_agent.md` | ネーム・企画のレビュー時 |
| 3 | `docs/harness.md` | ページ画像の生成・QA時 |
| 4 | `examples/demo-product/README.md` | 新規プロジェクト作成時 |

## ディレクトリマップ

```
manga/
├── agents/           # エージェント用システムプロンプト
├── tools/
│   ├── mangagen.py      # 制作ハーネス本体（lint/gen/qa/fix/assemble）
│   ├── manga_cli.py     # ホスト型プロバイダー CLI（login/token/gen）
│   ├── image_provider.py # 画像生成プロバイダー抽象化
│   └── build_prompt.py  # レビュー依頼プロンプト組み立て
├── server/              # ホスト型プロバイダー API（FastAPI + Supabase）
├── docs/
│   ├── knowledge/    # 制作知見の索引とポストモーテム記事
│   ├── harness.md    # mangagen の設計・使い方・失敗モード
│   ├── manga_principles.md       # 漫画原則
│   ├── manga_craft_research.md   # クラフト知見リサーチ集約
│   ├── review_checklist.md       # レビュー観点チェックリスト
│   ├── series_principles.md      # 連載漫画の原則
│   └── x_ads_manga_principles.md # X広告カルーセル形式の原則
├── templates/        # 入力テンプレート・クラフトガイド・series.json・レビューチェックリスト
├── projects/
│   └── onibaku/      # 連載漫画の実例（8話×16P）
├── examples/
│   └── demo-product/ # サンプルプロジェクト（2ページの読み切り）
└── tests/            # mangagen のユニットテスト
```

## タスク別のワークフロー

### A. 漫画脚本・ネーム・企画のレビュー（APIキー不要）

```bash
python3 tools/build_prompt.py --mode name-review path/to/draft.md
```

- システムプロンプト: `agents/manga_editor_agent.md`
- 判断基準: `docs/manga_principles.md`, `docs/review_checklist.md`, `docs/manga_craft_research.md`
- 出力を任意のLLMに貼り付けてレビューを実行

小説や長文記事を漫画化する場合は、いきなり `storyboard.json` を書かない。先に漫画脚本を作り、会話、反応、沈黙、サブテキストを固める。

推奨レイヤー（**各段階でレビューゲートを挟む。連続思考で飛ばさない**）:

```text
小説/原作 → 翻案設計 → 漫画脚本 → script_review.md → ネーム → name_review.md → storyboard.json → gen/qa
```

**禁止**: 脚本・ネーム・storyboard を同一セッションで一気に書くこと。  
脚本レビュー（ship）なしにネームへ、ネームレビュー（ship）なしに storyboard へ進めない。

各話の成果物:

- `production/spec/script.md`
- `production/spec/script_review.md`（チェックリスト: `templates/script_review_checklist.md`）
- `production/spec/name_v2.md`
- `production/spec/name_review.md`（チェックリスト: `templates/name_review_checklist.md`）
- `production/spec/storyboard.json`

漫画脚本で確認するもの:

- セリフ量が漫画として足りているか
- 重要な決断が会話の応酬になっているか
- 各セリフに相手の反応があるか
- 内面が目線、手元、距離、沈黙へ翻訳されているか
- ネームへ渡せる粒度になっているか

### B. ページ画像の生成（OpenRouter APIキーは画像出力だけ必要）

```bash
SPEC=examples/demo-product/manga/production/spec/storyboard.json

# パイプライン: lint → review(agent) → gen(OpenRouter image) → qa(agent) → fix(regen)
python3 tools/mangagen.py lint --spec $SPEC      # 無料・決定論的
python3 tools/mangagen.py review --spec $SPEC    # 無料・エージェント用レビュー依頼を生成

# ここで coding agent が output/latest/qa/review_request.md を読み、
# output/latest/qa/review.json を作成または更新する

export OPENROUTER_API_KEY=your_key              # 画像出力で必要
python3 tools/mangagen.py gen --spec $SPEC --pages 1,2  # 画像生成 ≈ $0.18/頁
python3 tools/mangagen.py qa --spec $SPEC        # 無料・エージェント画像QA依頼を生成

# ここで coding agent が page_XX_request.md と画像を見て page_XX.json を作成する

python3 tools/mangagen.py fix --spec $SPEC       # failページを再生成（画像出力なのでAPIキー必要）
python3 tools/mangagen.py assemble --spec $SPEC  # contact_sheet + book.pdf
```

**ホスト型プロバイダー**（運営サーバー経由・ユーザー側 OpenRouter キー不要）:

```bash
uv run manga login https://<hosted-api-url>
uv run manga token
uv run manga gen $SPEC -page 1 2
```

詳細: `docs/hosted-provider.md`

### C. 連載漫画（series-episode）

`projects/onibaku/` が実例。`manga/production/spec/series.json` に全話を定義し、各話は独立した storyboard.json を持つ。

```bash
SERIES=projects/onibaku/manga/production/spec
SPEC=projects/onibaku/manga/ep02-isourou/production/spec/storyboard.json

# 全話一括 lint
python3 tools/mangagen.py lint --series-root $SERIES

# 話単位パイプライン（読切と同型）
python3 tools/mangagen.py lint --spec $SPEC
python3 tools/mangagen.py review --spec $SPEC
python3 tools/mangagen.py gen --spec $SPEC --all-pages
python3 tools/mangagen.py qa --spec $SPEC
python3 tools/mangagen.py fix --spec $SPEC
python3 tools/mangagen.py assemble --spec $SPEC

# シリーズ横断レビュー（主要話の storyboard 揃い後）
python3 tools/mangagen.py series-review --series-root $SERIES
```

各話 storyboard には `"format": "series-episode"`, `"episode": N`, `"series": "slug"` を付ける。詳細は `docs/harness.md` の `format: series-episode` 節。

### D. 新規プロジェクトの作成

1. `examples/demo-product/` をコピーして `examples/<your-project>/` を作る
2. 小説・記事などの原作がある場合は、まず `script.md` を作る
3. `script_review.md` で脚本レビュー（ship までネーム禁止）
4. `script.md` からネームを作り、そこでページ配分・コマ割り・ヒキを決める
5. `name_review.md` でネームレビュー（ship まで storyboard 禁止）
6. `manga/production/spec/storyboard.json` を編集（キャラ・ページ・セリフ）
7. `templates/pro_panel_craft_base.md` を `pro_panel_craft.md` としてコピーし、演技節を作品用に書き換え
8. `lint` → `review` → `prompts` で事前検証してから `gen` を実行

## storyboard.json の構造

画像生成ハーネスに渡す単一ソース・オブ・トゥルース。小説や漫画脚本の代替ではない。主要フィールド:

```json
{
  "title": "作品名",
  "page_width": 1600,
  "page_height": 2400,
  "reading_direction": "rtl",
  "global_art_prompt": "画風の英語プロンプト",
  "characters": { "id": "英語の外見描写" },
  "quality_checks": ["QA用チェック項目"],
  "brand_strings": ["広告漫画のブランド名"],
  "format": "book",
  "series": "slug",
  "episode": 1,
  "pages": [
    {
      "page": 1,
      "beat": "ki",
      "panels": [
        {
          "id": "p01_01",
          "pos": "top-wide",
          "art": "英語の構図・演技指示",
          "dialogue": [{ "speaker": "名前", "text": "セリフ" }]
        }
      ]
    }
  ]
}
```

`format` に `"x-carousel"` を指定するとX広告カルーセルモードになり、`beat` は `hook` / `body` / `cta` を使います。

`format` に `"series-episode"` を指定すると連載各話モードになり、`series.json` と連携した lint/review が有効になります。生成レイアウトは `book` と同じです。

## 検出階層（3層）

| 層 | コマンド | 検出対象 | コスト |
|---|---|---|---|
| 構文 | `lint` / `lint --series-root` | スロット逆行、文字数超過、次話予告、話間キャラ増 | 無料 |
| 物語 | `review` + coding agent | フック、話単位変化量、前話連続性、ヒキメクリ | 無料 |
| シリーズ | `series-review` + coding agent | モチーフ追跡、話間整合、arc | 無料 |
| 実画像 | `qa` + coding agent | 文字化け、読み順、手の解剖、画面の物理 | 無料 |

**原則: 左（安い）で潰してから右（高い）に進む。**

## よくある失敗モード

`docs/harness.md` の「学んだ失敗モード」節を参照。特に重要:

- **max_tokens不足**: 既定16384。1024だと画像が返らず課金だけ発生
- **読み順逆転**: 2コマ横並びで右左が入れ替わる → `pos` スロット＋質問コマをワイドに
- **画面の物理違反**: PC天板に画面内容を描く → 肩越し構図を強制
- **QA過剰判定**: verdictの二値を信用せず、エラー内容の中身を読む

## テスト

```bash
uv run pytest
```

テストはインメモリの一時specを使い、APIキー不要。

## やってはいけないこと

- `output/` 配下の生成物をコミットしない（`.gitignore` 済み）
- APIキーをリポジトリに含めない
- `lint` を飛ばして `gen` を実行しない（課金前に構文エラーを検出できる）
- 散文のレイアウト指示だけに頼らない（`pos` スロットを必ず指定）

## 環境変数

| 変数 | 用途 |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter APIキー（`OPENROUTER` でも可）。画像出力する `gen` / `charsheet` / `fix` 用 |
| `OPENROUTER_MAX_TOKENS` | 生成時のmax_tokens（既定: 16384） |
| `MANGA_SUPABASE_URL` | ホスト型プロバイダー: Supabase プロジェクト URL |
| `MANGA_SUPABASE_ANON_KEY` | ホスト型プロバイダー: Supabase anon key |
| `MANGA_API_URL` | ホスト型プロバイダー API のベース URL |
