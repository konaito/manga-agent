# Manga Preview

`@yui540/comimi` を使って、生成済みの漫画ページをローカルブラウザで閲覧するためのプレビューです。

## 起動

```sh
cd preveiw
npm install
npm run sync:onibaku:all
npm run dev
```

表示されたローカルURLをブラウザで開くと、話数セレクトから第1話・第2話を切り替えて閲覧できます。

## URL で話数を指定

```text
http://127.0.0.1:5174/?ep=ep02
```

| パラメータ | 話 |
|---|---|
| `ep=ep01` | 第1話「呼び水」 |
| `ep=ep02` | 第2話「居候」 |

## 参照している画像

生成済み画像を `public/` に同期してから表示します。

```text
public/onibaku/ep01/pages/page_01.png … page_16.png
public/onibaku/ep02/pages/page_01.png … page_16.png
```

画像を再生成した場合:

```sh
npm run sync:onibaku:all      # 全話
npm run sync:onibaku          # 第1話のみ
npm run sync:onibaku:ep02     # 第2話のみ
```

## 新しい話を追加する

1. `npm run sync:onibaku:epXX` で `public/onibaku/epXX/` に同期
2. `src/episodes.ts` の `EPISODES` にエントリを追加
