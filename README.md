# AIの地図

会社どうしのつながりを「電力 → AIサービス」の6段階で見る地図サイトです。

## ファイル構成

- `index.html` … 画面（基本的に触らなくてよい）
- `data/map.json` … 地図の中身。更新はこのファイルだけ書き換える

## ローカルで確認する

`index.html` をダブルクリックで開くとデータを読み込めません。フォルダでターミナルを開き、次を実行してブラウザで表示されたURLを開いてください。

```
npx serve
```

## data/map.json の書き方

### 会社（nodes）

```json
{ "id": "nvda", "name": "NVIDIA", "layer": "chip", "jp": false, "size": "xl", "priv": false,
  "desc": "説明文（自分の言葉で2〜3行）" }
```

- `layer`：power / material / equip / chip / cloud / service のどれか
- `size`：xl（特大）/ l（大）/ m（中）
- `jp`：日本の会社なら true
- `priv`：非上場なら true

### つながり（edges）

```json
{ "id": "e1", "from": "tsmc", "to": "nvda", "type": "supply", "conf": 1,
  "text": "なぜつながっているかの解説",
  "status": "原本確認済み",
  "sources": [
    { "title": "TSMC 2025年 年次報告書", "url": "https://...", "type": "一次情報", "date": "2026-03-01" }
  ] }
```

- `type`：supply（取引・供給）/ comp（競合）/ impact（影響）
- `conf`：1（確認済み）/ 2（一般的な見方）/ 3（仮説）
- `status`：未確認 / 原本確認済み / 報道で確認 など
- `sources.type`：一次情報（決算・有報・会社発表）/ 報道 / その他

`conf` を 1 にしてよいのは、`sources` に一次情報か信頼できる報道が入っているときだけ。

### 出来事（events）

`layers` に影響する段階を並べる。`x` は横位置（260〜960くらい）。

### 今週の変化（changes）

```json
{ "label": "線を追加：SK hynix → NVIDIA", "edge": "e2" }
```

`edge` / `event` / `node` のどれかでクリック先を指定する。

## 公開前チェック

- [ ] すべての線の `status` が「未確認」以外になっている
- [ ] 説明文・解説文を自分の言葉で書き直した
- [ ] 裏が取れなかった線は `conf: 3` に下げるか削除した
- [ ] `changes` を実際の更新内容に差し替えた（表示例の文言を消す）
