# シリーズ横断レビュー・チェックリスト

`series-review` 実行後、全話の storyboard が揃っている段階（または主要話が ship 済み）でエージェントがこのチェックリストでレビューする。

成果物: `manga/production/output/latest/qa/series_review.json`

## 判定

- **ship**: 各話の生成・画像QAへ進める（または続行）
- **revise**: 特定話の脚本 / ネーム / storyboard へ戻る

## チェック項目

### シリーズ arc

- [ ] 第1話開始状態 ↔ 最終話終了状態の変化量が adaptation_design と一致
- [ ] 各話が **1つの問題** だけを扱っている（手口・段階の取り違えがない）
- [ ] 説明セリフで横取り手口等を長々と説明していない

### 各話 emotional_delta

- [ ] 各話の `emotional_delta`（series.json）が storyboard の1P目↔最終Pで達成されている
- [ ] adaptation_design の話数表と矛盾がない

### モチーフ追跡

- [ ] story bible の反復モチーフが、話をまたいで初出・変質している
- [ ] 各話の `quality_checks` にモチーフ追跡が書かれている

### 話間整合

- [ ] キャラ設定（性別・外見・禁止事項）が story bible と全話で一致
- [ ] 前話末 ↔ 次話始まりの状態が連続している
- [ ] 新キャラ登場が1話1人以内（急増していない）

### ヒキ接続

- [ ] 各話ヒキ（adaptation_design）が次話 premise と接続している
- [ ] 最終話以外: 最終ページに次話予告がある
- [ ] 最終話: 次話予告がなく、余韻・タイトル回収で終わる

## レビュー記録フォーマット

```md
# シリーズレビュー

- 判定: ship | revise
- レビュー日:
- 入力: series.json + 全話 storyboard 要約

## 良い点

## 話別メモ

## 修正必須

## 修正推奨
```

JSON 出力は `series_review_request.md` の指示に従う。
