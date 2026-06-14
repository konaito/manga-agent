# デモプロジェクト: はじめてのタスク管理

mangagen ハーネスの動作確認用サンプルです。架空のプロダクト「TaskFlow」を題材にした2ページの読み切り漫画です（`format: book` 既定）。

連載漫画の例は `projects/onibaku/` を参照。`format: series-episode` と `series.json` の使い方は `docs/harness.md` を見てください。

## ディレクトリ構成

```
examples/demo-product/
└── manga/production/
    ├── spec/
    │   ├── storyboard.json      # 単一ソース（ページ・コマ・セリフ・品質チェック）
    │   └── pro_panel_craft.md   # 生成プロンプトに注入するクラフトガイド
    └── output/                  # 生成物（gitignore対象）
        └── latest/
```

## 使い方

```bash
SPEC=examples/demo-product/manga/production/spec/storyboard.json

# 決定論的チェック（無料）
python3 tools/mangagen.py lint --spec $SPEC

# プロンプト確認（無料）
python3 tools/mangagen.py prompts --spec $SPEC

# ページ生成（課金。OPENROUTER_API_KEY が必要）
python3 tools/mangagen.py gen --spec $SPEC --pages 1,2

# エージェント画像QA依頼（無料）
python3 tools/mangagen.py qa --spec $SPEC

# coding agentが output/latest/qa/page_XX_request.md と画像を見て page_XX.json を作る
```

## 新規プロジェクトの作り方

1. このディレクトリをコピーする
2. `storyboard.json` のキャラ・ページ・セリフを書き換える
3. `pro_panel_craft.md` の演技節・禁止節を作品用に調整する
4. `templates/pro_panel_craft_base.md` を参照して不足があれば追記する
