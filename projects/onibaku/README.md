# 鬼畜 — 自分の悪意が見えなくなる日

原作: [note記事](https://note.com/konaito_/n/n8b833a165414)

連載漫画（全8話 × 16ページ）。

## 話数

| 話 | ディレクトリ | 状態 |
|---|---|---|
| 第1話 夜の呼び水 | `manga/ep01-yobimizu/` | 脚本から再設計 |
| 第2話 居候 | `manga/ep02-isourou/` | **16P 生成済**（`production/output/latest/`） |
| 第3話 青い光 | `manga/ep03-aoihikari/` | 未着手 |
| 第4話 四百円 | `manga/ep04-yonhyakuen/` | 未着手 |
| 第5話 小口現金 | `manga/ep05-koguchigenkin/` | 未着手 |
| 第6話 反復の速度 | `manga/ep06-kurikaeshi/` | 未着手 |
| 第7話 原稿 | `manga/ep07-genkou/` | 未着手 |
| 第8話 十三件目 | `manga/ep08-juusankenme/` | 未着手 |

## 設計ドキュメント

- `脚本.md` — 話数索引と旧ネーム案
- `manga/production/spec/adaptation_design.md` — 連載化の全体設計
- `manga/production/spec/story_bible.md` — キャラ・モチーフ・禁止事項
- `manga/production/spec/script_framework.md` — 小説を漫画脚本へ変換する型
- `manga/production/spec/workflow.md` — 小説→脚本→ネーム→生成の制作工程

## 制作方針

小説を直接 `storyboard.json` に圧縮しない。各話ごとに `production/spec/script.md` を作り、会話、反応、沈黙、サブテキストを固めてからネームと `storyboard.json` に進む。

第1話の既存生成画像は、ヒロの性別設定ミスとセリフ量不足が分かったため旧版扱い。正式版は男性2人の会話劇として脚本から作り直す。

第1話の新しい脚本:

- `manga/ep01-yobimizu/production/spec/script.md`

## 第1話の生成

```bash
SPEC=projects/onibaku/manga/ep01-yobimizu/production/spec/storyboard.json

python3 tools/mangagen.py lint --spec $SPEC
python3 tools/mangagen.py review --spec $SPEC

# coding agentが output/latest/qa/review_request.md を読んで review.json を作る

export OPENROUTER_API_KEY=your_key_here
python3 tools/mangagen.py gen --spec $SPEC --all-pages

# エージェント画像QA依頼（無料）
python3 tools/mangagen.py qa --spec $SPEC

# coding agentが output/latest/qa/page_XX_request.md と画像を見て page_XX.json を作る

python3 tools/mangagen.py assemble --spec $SPEC
```
