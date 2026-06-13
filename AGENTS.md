# AGENTS.md — AIエージェント向けリポジトリガイド

このファイルは、AIエージェント（Cursor、Claude Code、Codex 等）がこのリポジトリを初めて見たときに読むためのガイドです。

## このリポジトリは何か

**Manga Agent** は2つの機能を持つオープンソースツールキットです。

1. **漫画編集者エージェント** — 企画・ネーム・読み切り構成をレビューするためのプロンプトパック
2. **mangagen 制作ハーネス** — storyboard JSON を単一ソースとして、AI画像生成→ビジョンQA→自動リロールまで行うCLI

特定のLLMベンダーに依存しません。OpenRouter API経由で画像生成・ビジョンQAを行います。

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
│   ├── mangagen.py   # 制作ハーネス本体（lint/gen/qa/fix/assemble）
│   └── build_prompt.py  # レビュー依頼プロンプト組み立て
├── docs/
│   ├── knowledge/    # 制作知見の索引とポストモーテム記事
│   ├── harness.md    # mangagen の設計・使い方・失敗モード
│   ├── manga_principles.md       # 漫画原則
│   ├── manga_craft_research.md   # クラフト知見リサーチ集約
│   ├── review_checklist.md       # レビュー観点チェックリスト
│   └── x_ads_manga_principles.md # X広告カルーセル形式の原則
├── templates/        # 入力テンプレート・クラフトガイドのベース
├── examples/
│   └── demo-product/ # サンプルプロジェクト（2ページの読み切り）
└── tests/            # mangagen のユニットテスト
```

## タスク別のワークフロー

### A. ネーム・企画のレビュー（APIキー不要）

```bash
python3 tools/build_prompt.py --mode name-review path/to/draft.md
```

- システムプロンプト: `agents/manga_editor_agent.md`
- 判断基準: `docs/manga_principles.md`, `docs/review_checklist.md`, `docs/manga_craft_research.md`
- 出力を任意のLLMに貼り付けてレビューを実行

### B. ページ画像の生成（OpenRouter APIキー必要）

```bash
export OPENROUTER_API_KEY=your_key

SPEC=examples/demo-product/manga/production/spec/storyboard.json

# パイプライン: lint → review → gen → qa → fix
python3 tools/mangagen.py lint --spec $SPEC      # 無料・決定論的
python3 tools/mangagen.py review --spec $SPEC    # テキストLLM ≈ $0.05
python3 tools/mangagen.py gen --spec $SPEC --pages 1,2  # 画像生成 ≈ $0.18/頁
python3 tools/mangagen.py qa --spec $SPEC        # ビジョンQA ≈ $0.0012/頁
python3 tools/mangagen.py fix --spec $SPEC       # QA失敗ページの自動リロール
python3 tools/mangagen.py assemble --spec $SPEC  # contact_sheet + book.pdf
```

### C. 新規プロジェクトの作成

1. `examples/demo-product/` をコピーして `examples/<your-project>/` を作る
2. `manga/production/spec/storyboard.json` を編集（キャラ・ページ・セリフ）
3. `templates/pro_panel_craft_base.md` を `pro_panel_craft.md` としてコピーし、演技節を作品用に書き換え
4. `lint` → `prompts` で事前検証してから `gen` を実行

## storyboard.json の構造

単一ソース・オブ・トゥルース。主要フィールド:

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

## 検出階層（3層）

| 層 | コマンド | 検出対象 | コスト |
|---|---|---|---|
| 構文 | `lint` | スロット逆行、文字数超過、禁止文字列、起承転結配分 | 無料 |
| 物語 | `review` | フック、変化量、論理穴、ヒキメクリ | ≈ $0.05/冊 |
| 実画像 | `qa` | 文字化け、読み順、手の解剖、画面の物理 | ≈ $0.0012/頁 |

**原則: 左（安い）で潰してから右（高い）に進む。**

## よくある失敗モード

`docs/harness.md` の「学んだ失敗モード」節を参照。特に重要:

- **max_tokens不足**: 既定16384。1024だと画像が返らず課金だけ発生
- **読み順逆転**: 2コマ横並びで右左が入れ替わる → `pos` スロット＋質問コマをワイドに
- **画面の物理違反**: PC天板に画面内容を描く → 肩越し構図を強制
- **QA過剰判定**: verdictの二値を信用せず、エラー内容の中身を読む

## テスト

```bash
python3 -m pytest tests/
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
| `OPENROUTER_API_KEY` | OpenRouter APIキー（`OPENROUTER` でも可） |
| `OPENROUTER_MAX_TOKENS` | 生成時のmax_tokens（既定: 16384） |
