# 鬼畜 — 連載化設計

## なぜ8話×16Pか

原作は約3,000行・5幕の文学小説。16P読み切り1冊では第二幕の「段階的横領」と第三幕の「反復の速度」が消える。
連載8話（計128P）なら、各幕を1〜2話に割り当て、原作の**構造**を保ったまま漫画の情報量に収まる。

## 話数一覧

| 話 | タイトル | 原作パート | 頁 | この話の変化 |
|---|---|---|---|---|
| **1** | 夜の呼び水 | プロローグ | 16 | 衝動の一言 → 玄関に他人の荷物 |
| **2** | 居候 | 第一幕・前半 | 16 | 一晩の客 → 「うん」で儀式化 |
| **3** | 青い光 | 第一幕・後半 | 16 | iPhone譲渡 → 見ない選択の確立 |
| **4** | 四百円 | 第二幕・前半 | 16 | 経費混同 → 気づかれない感触 |
| **5** | 小口現金 | 第二幕・後半 | 16 | 信頼される → 解雇・Instagram服 |
| **6** | 反復の速度 | 第三幕・前半 | 16 | 転職 → 架空振込・逮捕 |
| **7** | 原稿 | 第三幕・後半 | 16 | 留置の電話 → 執行猶予・電話の終わり |
| **8** | 十三件目 | エピローグ | 16 | 倉庫勤務 → メルカリを開く |

## 各話の終わり方（ヒキ設計）

- **第1話**: 玄関の隅にスポーツバッグ。「最初の異常」モノローグ。
- **第2話**: 「家、絶対すぐ探します」に「うん」と答える。二年の始まり。
- **第3話**: 服が増えているのを見て、見ようとしなかった。
- **第4話**: 社長から小口現金を任された夜。「嬉しい」を信じた。
- **第5話**: 解雇。彼が「合わなくて」と言う。私は聞かなかった。
- **第6話**: 手錠。または留置場の扉。
- **第7話**: 「もう、迷惑かけません」— 信じることにした。
- **第8話**: メルカリを開く指。タイトル回収。余韻で終わる（説明しない）。

## ページ配分の原則（各話16P）

- 起 4P / 承 4P / 転 5P / 結 3P（読み切りと同型だが、**話末は次話へのヒキ**で終える）
- 1話あたり新キャラ登場は1人まで（第6話の社長・警察などはシルエット可）
- 1話あたり扱う問題は1つ（横領の手口は1段階ずつ）

## ディレクトリ構成

```
projects/onibaku/
├── README.md
├── 脚本.md                    # シリーズ全体の索引
├── source/
│   ├── source_meta.json
│   └── original.md            # 原作テキスト（参照用）
└── manga/
    ├── ep01-yobimizu/
    │   └── production/spec/storyboard.json
    ├── ep02-isourou/
    ├── ep03-aoihikari/
    ├── ep04-yonhyakuen/
    ├── ep05-koguchigenkin/
    ├── ep06-kurikaeshi/
    ├── ep07-genkou/
    └── ep08-juusankenme/
```

## 制作パイプライン（話ごと）

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

python3 tools/mangagen.py fix --spec $SPEC
python3 tools/mangagen.py assemble --spec $SPEC
```

## 第2話以降の先行作業

第1話の `storyboard.json` が通ったら、第2話は第一幕227行目「彼は面接に受かった」から着手。
第1話末のキャラ外見・部屋レイアウトを `reference_images` に固定し、話をまたいだ一貫性を取る。
