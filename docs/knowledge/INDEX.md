# Knowledge Index

タスク着手前にここを見る。関連があれば articles/ の該当記事を先に読む。

## クラフト（漫画の作り方）

- [漫画クラフト知見・リサーチ集約](../manga_craft_research.md) — 視線誘導 / ヒキメクリ / コマ大小 / ページ配分比率 / セリフ術（松井・青山） / 説明セリフ回避 / 河原和音の起承実務 / 読切2大必須 / 構成チェック。**reviewコマンドの判断基準**
- [漫画原則](../manga_principles.md) — 一致と分割 / 関係性 / 変化量 / メリット−コスト
- [ジャンプ漫画学校原則](../jump_manga_school_principles.md) — 冒頭の大きい絵 / フキダシ導線 / TPO
- [レビューチェックリスト](../review_checklist.md) — 企画 / ネーム / キャラ / 読み切り / AI生成の観点
- [X広告カルーセル原則](../x_ads_manga_principles.md) — 検証済み公式仕様（1:1 / 2〜6枚 / 280 weighted）/ hook→body→cta / 広告色抑制と事例 / モバイル可読性。**format: x-carousel のreview判断基準**

## ハーネス（作る仕組み）

- [mangagen制作ハーネス](../harness.md) — 設計思想（lint→review→gen→qa→fix）/ 使い方 / 失敗モード
- [記事: AI生成漫画の検品観点](articles/visual-qa-checklist.md) — 実制作6冊から蓄積した11観点（画面の物理・手・読み順・ブランド露出ほか）と判定の運用
- [記事: 読み順逆転ポストモーテム](articles/production-postmortem-reading-order.md) — 読み順逆転とmax_tokens地雷
- [記事: デュアルPOVポストモーテム](articles/production-postmortem-dual-pov.md) — デュアルPOV設計とQA較正

## 運用メモ

- APIキー: `OPENROUTER_API_KEY` または `OPENROUTER` 環境変数
- 実測コスト: 生成 ≈ $0.18/頁、ビジョンQA ≈ $0.0012/頁、編集レビュー ≈ $0.05/冊
