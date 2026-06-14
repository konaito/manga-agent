# mangagen 制作ハーネス

`tools/mangagen.py` は、スペックJSON（storyboard）を単一ソースとする漫画制作ハーネス。
スペックJSON（storyboard）は画像生成工程の単一ソースであり、小説や漫画脚本の代替ではない。

## 設計思想（ハーネスエンジニアリングの原則を適用）

ハーネス設計の一般原則（Fowler「Harness engineering」、evaluator-optimizerパターン等）をこのドメインに落とした構成:

1. **二層制御 = feedforward + feedback**: 事前制御（スペック・スロット・テキスト契約・lint）と事後検証（エージェント画像QA）の両方を持つ。事前だけでは効果が検証されず、事後だけでは同じ誤りを繰り返す。
2. **決定論的レイヤーと推論的レイヤーの分離**: `lint` は純Pythonの確定チェック（無料・即時・確実）、`review` / `qa` はコーディングエージェントが判断するための依頼パック生成（無料）。OpenRouterは画像出力だけに使う。
3. **生成と評価の分離**: 生成モデルは自己採点が甘い。生成後はcoding agentが画像とspecを見比べ、構造化JSON（grid転記→reader順走査→verdict）で判定する。
4. **フィードバックは具体的修正指示として返す**: `fix` の再生成プロンプトには保存済みQA結果の個別エラー（「この文字列が欠落」「このコマが逆順」）を `PREVIOUS ATTEMPT FAILED QA` ブロックとして注入する。盲目リトライをしない。
5. **ループには打ち切りとエスカレーション**: `fix` は再生成後に新しいQA依頼を作り、追加判断をcoding agentへ戻す。自動で外部QAを回さない。
6. **best-of-Nは無効化**: 候補選択には画像QAが必要なため、OpenRouterを画像出力だけに限定する現在の設計では `--candidates > 1` を拒否する。
7. **生成仕様はstoryboard JSONに集約**: ページ・コマ・キャスト識別子・品質チェック・参照画像をstoryboard JSONに持つ。小説や漫画脚本の試行錯誤は前段で済ませ、キャストが変わってもツールは編集しない。
8. **コマ位置はスロットで明示**: 各panelの `pos`（`top-wide` / `row2-right` 等）をプロンプトに明記。研究側（DiffSensei等）のレイアウト条件付け・キャラ識別アダプタに対する、API利用での実務的等価物が「明示スロット＋キャラ参照画像＋正確テキスト契約」。
9. **観測可能性**: 画像出力API呼び出しと、無料のreview/qa依頼生成を `output/ledger.jsonl` に記録（時刻・コマンド・ページ・コスト・判定）。1冊いくらかかったかが常に分かる。
10. **出力はlatest一本**: `output/latest/` が常に最新の本。置き換え前ページは `output/history/` に退避。run dir連鎖を作らない。

## 使い方

ハーネス内部のパイプライン: **lint（決定論） → review（エージェント用レビュー依頼） → gen（OpenRouter画像生成） → qa（エージェント用画像QA依頼） → fix（フィードバック付き再生成）**。
左ほど安く、左で潰した問題ほど節約効果が大きい（lint/review=無料、gen≈$0.18/頁）。

小説や長文記事の漫画化では、ハーネスの前に **漫画脚本 → ネーム** を置く。小説を直接 `storyboard.json` に圧縮すると、会話の応酬、反応、沈黙、サブテキストが不足しやすい。

```bash
SPEC=examples/demo-product/manga/production/spec/storyboard.json

# 決定論的チェック（無料・即時）。genは内部でも実行し、errorがあると課金前に止まる
python3 tools/mangagen.py lint --spec $SPEC

# 編集者レビュー依頼（無料）。OpenRouterは使わず、coding agentが読むための
# output/latest/qa/review_request.md と review_payload.json を生成する
python3 tools/mangagen.py review --spec $SPEC

# coding agentが review_request.md を読んで output/latest/qa/review.json を作る。
# プロンプトだけ書き出す（無料の検証）
python3 tools/mangagen.py prompts --spec $SPEC

# ページ生成（課金）。全ページは --all-pages を明示
python3 tools/mangagen.py gen --spec $SPEC --pages 1,8
python3 tools/mangagen.py gen --spec $SPEC --all-pages

# エージェント画像QA依頼（無料）。output/latest/qa/page_XX_request.md を生成
python3 tools/mangagen.py qa --spec $SPEC

# coding agentが page_XX_request.md と画像を見て page_XX.json を作る

# QA failページをエラー内容フィードバック付きで再生成（画像生成なのでOpenRouterを使う）
python3 tools/mangagen.py fix --spec $SPEC --attempts 2

# contact_sheet.png と book.pdf を再構築
python3 tools/mangagen.py assemble --spec $SPEC

# キャラ参照シート生成 → 目視で識別子を確認してから spec の "reference_images" に追加
python3 tools/mangagen.py charsheet --spec $SPEC
```

`lint` が見るもの: posスロットの逆行・未知値、**横並びコマでの質問→応答分割**（実制作で最多のリロール原因。
モデルが右左を入れ替えやすい）、同一ページ内の重複文字列、ページあたり文字列数（8でwarn、12でerror）、
空セリフ、`forbidden_strings` の混入、**吹き出し40字超**（3〜4行×10〜11字の可読限界）、
**ページ150字超**（読者コスト指標）、**1ページ8コマ超**、
**起承転結の配分**（ページに `"beat": "ki"|"sho"|"ten"|"ketsu"` を付けると、起1/4・承1/4・転1/3・結1/8
からの大幅逸脱をwarn、順序違反をerror、結＞転をwarnで検出）。

`review` が依頼パックに含めるもの（`docs/manga_craft_research.md` ほか編集原則4文書を基準に）: 最初の5ページのフック、
1ページ目↔最終ページの変化量、キャラの好感度形成、起承転結配分（起1/4・承1/4・転1/3・結1/8）、
全ページのヒキ/メクリ、大ゴマの序中盤配置、**ページをまたぐ論理穴**。実走では「P14で大和がフルネームを
知っている根拠が作中にない」というlintにもビジョンQAにも検出不能な設定穴を発見した。
検出階層の整理: **lint=構文、review=物語、qa=実画像**。

APIキーは画像出力を行う `gen` / `charsheet`、および失敗ページを再生成する `fix` でのみ必要。`OPENROUTER_API_KEY` または `OPENROUTER` 環境変数に設定する。`review` と `qa` はAPIキー不要。
`max_tokens` の既定は16384（画像トークンが約5,700消費されるため。旧版の1024は画像が返らず課金だけ発生する地雷だった）。

## format: x-carousel（X広告カルーセル）

スペックに `"format": "x-carousel"` を書くと広告モードになる。`pages` の1要素 = カルーセルの1カード。

- 生成は 1:1（canvas推奨 1080×1080）。カード間は左→右スワイプ、カード内のコマ読みは rtl 固定
- beat語彙は `hook` / `body` / `cta`（起承転結のki/sho/ten/ketsuと排他）
- lint追加分: カード2〜6枚（範囲外error）/ 1枚目hook・最終枚cta（欠落warn）/ cta中間出現warn /
  カード80字warn・120字error / カード4コマ超warn / `ad_copy` 280 weighted超error / 非正方形canvas warn
- reviewは `docs/x_ads_manga_principles.md` を判断基準に追加した依頼パックを生成し、coding agentがhook→body→ctaで評価
- assembleはスワイプ順の横一列 contact_sheet.png と ad_copy.txt を出力（book.pdfは作らない）

判断基準・公式仕様の出典は [X広告カルーセル原則](x_ads_manga_principles.md)。

## format: series-episode（連載漫画）

連載の各話は `format: "series-episode"` の storyboard.json を1話1ファイルで持つ。生成・assemble は読切（`book`）と同じ（2:3 ページ、book.pdf）。

### シリーズルート `series.json`

`manga/production/spec/series.json` に全話一覧・story bible パス・各話の `emotional_delta` を置く。テンプレート: `templates/series.json`。

```jsonc
{
  "title": "作品タイトル",
  "slug": "my-series",
  "story_bible": "story_bible.md",
  "adaptation_design": "adaptation_design.md",
  "episodes": [
    {
      "number": 1,
      "slug": "ep01-first",
      "title": "第1話タイトル",
      "spec": "../../ep01-first/production/spec/storyboard.json",
      "emotional_delta": "開始 → 終了"
    }
  ]
}
```

各話 storyboard には `"format": "series-episode"`, `"series": "slug"`, `"episode": N`, `"series_root": "../../../production/spec"`（任意・省略時は上方向に `series.json` を自動探索）を付ける。

### lint（話単位 + 一括）

```bash
SPEC=projects/onibaku/manga/ep02-isourou/production/spec/storyboard.json
python3 tools/mangagen.py lint --spec $SPEC

# 全話一括（series.json に列挙された spec を順に lint + 話間チェック）
python3 tools/mangagen.py lint --series-root projects/onibaku/manga/production/spec
```

`series-episode` 追加分:

- `episode` 必須（error）
- `series.json` との整合（話番号・spec パス）
- 最終話以外: 最終ページに次話予告（「続く」または `第N+1話`）（warn）
- 最終話: 次話予告がある（warn）
- 第2話以降: 前話比でキャラ2人以上増（warn）、`quality_checks` に継続ヒントなし（warn）

### review（話単位）

```bash
python3 tools/mangagen.py review --spec $SPEC
```

読切の「完結満足」ではなく、**話単位の emotional_delta・前話連続性・次話ヒキ**で評価。`docs/series_principles.md` を判断基準に追加。payload に `prev_episode_final`（前話最終ページ）を同梱。

### series-review（シリーズ横断）

主要話の storyboard が揃った段階で:

```bash
python3 tools/mangagen.py series-review --series-root projects/onibaku/manga/production/spec
# → manga/production/output/latest/qa/series_review_request.md
# coding agent が series_review.json を作成
```

チェックリスト: `templates/series_review_checklist.md`（モチーフ追跡・話間整合・シリーズ arc）。

### 連載のレビューゲート（人手）

| 段階 | 成果物 | チェックリスト |
|---|---|---|
| 脚本 | `script_review.md` | `templates/script_review_checklist.md` |
| ネーム | `name_review.md` | `templates/name_review_checklist.md` |
| storyboard | `review.json` | mangagen review（連載観点） |
| 全話 | `series_review.json` | series-review |

実例: `projects/onibaku/`

## スペックJSONの拡張フィールド

```jsonc
{
  "title": "...",
  "format": "book | x-carousel | series-episode",
  "series": "slug",              // series-episode のみ
  "episode": 2,                    // series-episode のみ
  "series_root": "../../../production/spec",
  "global_art_prompt": "...",
  "characters": { "name": "識別子を含む英語記述。LINEアイコン等もここ" },
  "quality_checks": ["プロンプトのQUALITY CHECKとエージェント画像QAの両方に注入される行"],
  "reference_images": ["character_sheet.png"],   // 任意。全gen callに添付
  "craft_guide": "pro_panel_craft.md",           // 任意。spec同階層から読む
  "pages": [{
    "page": 1, "title": "...", "layout": "hook4",
    "panels": [{
      "id": "p01_01",
      "pos": "top-wide",        // top-wide / row1-right / row1-left / row2-* / row3-* / middle-wide / bottom-wide
      "art": "英語のコマ演出指示",
      "dialogue": [
        {"speaker": "名前", "text": "セリフ"},
        {"kind": "ui|caption|monologue|sfx|text", "text": "..."}
      ]
    }]
  }]
}
```

## 制作ワークフロー（推奨）

1. 原作が小説・記事の場合は、まず漫画脚本（script.md）を作る。会話、反応、沈黙、サブテキスト、ページごとの読者感情を固める
2. ネーム文書（name_vX.md）で構成を固める。読み順事故を防ぐため、質問→応答が2コマ横並びになるビートは、質問側を `top-wide` にするか同一コマに収める
3. ネームで決めた内容を `storyboard.json` に落とす
4. `lint` / `review` / `prompts` で生成前検証を行う
5. `gen --pages` でフックページと見せ場ページ（例: 1とクライマックス）だけ試し、画風と文字精度を確認
6. 残りページを `gen`
7. `qa` → coding agentが `page_XX_request.md` と画像を見て `page_XX.json` を作る → failがあれば `fix`
8. 自分の目でもcontact sheetと全ページを見る（QAは較正済みだが万能ではない。意味の通る誤読み順はwarnに落ちる）
9. `assemble` で book.pdf

漫画脚本レビューで見るもの:

- セリフが少なすぎないか
- 重要な決断が会話の応酬として成立しているか
- 各セリフに相手の反応があるか
- 内面が視線、手元、距離、姿勢、道具へ翻訳されているか
- モノローグが説明ではなく自己欺瞞を担っているか
- セリフ・モノローグ・地の文の**容器形状**がページを通して統一されているか（`docs/bubble_render_research.md`）

## 知見の蓄積ルール

- 制作1本ごとにポストモーテムを `docs/knowledge/articles/` に書き、`docs/knowledge/INDEX.md` から張る
- 「人間判断で済ませた回避策」は次の制作前に lint / review / craft guide のどれかへ機械化できないか検討する
  （例: ワイド1コマ目の手動指定 → posスロット＋lint、配分の目視確認 → beatタグ＋lint）
- 検出階層の原則: **構文の問題はlint、物語の問題はreview、実画像の問題はqa**。
  下の階層（安い側）に降ろせる知見ほど価値が高い

## 漫画クラフト知見の置き場所

- `docs/manga_craft_research.md`: リサーチ集約（視線誘導・ヒキメクリ・コマ大小・配分比率・文字数の出典つき数値）。reviewコマンドが読む
- `templates/pro_panel_craft_base.md`: 新規企画用クラフトガイドのベース。specディレクトリにコピーして演技節を作品用に書き換える
- `examples/*/manga/production/spec/pro_panel_craft.md`: 作品別。全生成プロンプトに注入される
- 既存の `docs/manga_principles.md` / `docs/jump_manga_school_principles.md` / `docs/review_checklist.md` もreviewの判断基準として自動で読み込まれる

## 参考にした設計知見

- Martin Fowler / Thoughtworks「Harness engineering」: feedforward/feedback二層、計算的制御と推論的制御の分離、修正指示入りエラーメッセージ、keep quality left — https://martinfowler.com/articles/harness-engineering.html
- Evaluator-Optimizerパターン: 生成と評価の分離、構造化verdict、打ち切り条件とエスカレーション — https://www.agentpatterns.ai/agent-design/evaluator-optimizer/
- LangChain「The Anatomy of an Agent Harness」: 検証ループ・状態管理・人間介入ポイントの整理 — https://www.langchain.com/blog/the-anatomy-of-an-agent-harness
- DiffSensei (CVPR 2025): レイアウト条件付け＋キャラ識別制御が研究側の主流。API利用での等価物＝明示スロット＋参照画像＋テキスト契約 — https://arxiv.org/abs/2412.07589
- 実務者知見（AIコミック制作ガイド各種）: キャラ一貫性が品質の最重要因子、スタイル見本とキャラシートを本編より先に作る
- 漫画クラフト出典は `docs/manga_craft_research.md` の出典節を参照（齊藤優・ジャンプの漫画学校・ページ配分論・視線誘導論ほか）

## 学んだ失敗モード（重要）

- **読み順逆転**: 2コマ横並びで右左が入れ替わる。スロット明示＋「質問コマをワイドにする」構成側の回避が効く
- **max_tokens不足**: 画像が返らないのに課金される
- **QAの過剰判定**: スロット一致と読み順を混同する。判定手順を「grid転記→reader順を歩く」の2段に分けると安定する
- **キャラシートの欠陥伝播**: 参照画像に識別子の欠け（眼鏡なし等）があると全ページに伝播する。specに繋ぐ前に必ず目視
- **reviewのverdictは判断材料**: coding agentのレビューでも二値判定だけを信用せず、**top_fixesの中身**を読んで人間が採否を決める。指摘は生成前に構造問題を潰すためのもの
- **画面がデバイスの裏側に描かれる**: モデルが「キャラの顔」と「画面の文字」を両方正面から見せようとして、ノートPC天板やスマホ背面に画面内容を描く。対策: 読ませる画面のコマは**肩越し・覗き込み構図**か**画面単体インサート**を構図指示で強制。craft guide「画面の物理」節＋プロンプトのSCREEN PHYSICS節＋QAチェック7として三層で恒久化済み
- **ブランド名の露出不足**: 物語に集中するとサービス名をスペックから落とす。広告漫画では機能欠陥。lintの`brand_strings`チェック（0回=error、1回/最終ページのみ=warn）で恒久化済み
