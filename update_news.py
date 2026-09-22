"""
業界勢力図：毎週のニュース自動更新スクリプト

やること
1. industries.json にある業界ごとに、<業界id>.json を読み込む
2. Claude API（Web検索つき）に、直近7日間の主要企業ニュースを探して要約・判定させる
3. 検索結果に実際に出てきたURLだけを出典として認める（存在しない記事を防ぐ）
4. 「続いているテーマ」（ongoing）は残し、それ以外のニュースを今週分に入れ替える
5. 古いデータは archive/ に保存する
"""
import json, os, re, sys, datetime
import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES", "8"))
JST = datetime.timezone(datetime.timedelta(hours=9))

client = anthropic.Anthropic()  # APIキーは環境変数 ANTHROPIC_API_KEY から読む


def jp_date(d):
    return f"{d.year}年{d.month}月{d.day}日"


def build_prompt(ind, start, end):
    companies = "\n".join(f'- id: {c["id"]} / {c["name"]}：{c.get("note","")}' for c in ind["companies"])
    return f"""あなたは投資家向けニュースメディア「業界勢力図」の編集者です。
業界「{ind["name"]}」について、{jp_date(start)}から{jp_date(end)}までの7日間に出たニュースを、Web検索で集めてください。

## 対象の会社
{companies}

## 集め方のルール
- 上の会社に関係するニュースだけを選ぶ。期間外のニュースは入れない。
- 各社の公式発表（ニュースリリース・IR）と、大手の報道機関の記事を優先する。個人ブログ、まとめサイト、Googleニュースのページは出典にしない。
- 重要度の高いものから最大12件。見つからなければ少なくてよい（0件でもよい）。
- 同じ出来事を扱う記事は1件にまとめる。

## 書き方のルール
- title：22文字以内。元の記事の見出しをそのまま使わず、自分の言葉で書く。
- summary：2〜3文。元の記事の文章を写さず、事実だけを自分の言葉で要約する。推測や投資の勧めは書かない。
- companies：そのニュースが各社の業績や株価にとって追い風なら dir: 1、向かい風なら dir: -1。判断がつかない会社は入れない。
- confidence：「公式発表」「報道」「統計」のどれか。
- tags：国名やテーマなど、短いラベルを0〜3個。
- sources：実際に検索結果に出てきた記事のURLとタイトル（媒体名と日付）。URLを作ったり推測したりしない。

## 出力
最後に、次の形のJSONだけを ```json と ``` で囲んで出力してください。
````json
{{"news":[{{"date":"YYYY-MM-DD","title":"...","summary":"...","confidence":"報道","companies":[{{"id":"会社id","dir":1}}],"tags":["..."],"sources":[{{"title":"媒体名（YYYY年M月D日）","url":"https://..."}}]}}]}}
```"""


def run_claude(prompt):
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES,
              "user_location": {"type": "approximate", "country": "JP", "timezone": "Asia/Tokyo"}}]
    seen_urls, texts = set(), []
    for _ in range(6):  # 長い検索で一時停止（pause_turn）したら続ける
        resp = client.messages.create(model=MODEL, max_tokens=8000, messages=messages, tools=tools)
        for block in resp.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                for r in block.content:
                    url = getattr(r, "url", None)
                    if url:
                        seen_urls.add(url)
            elif block.type == "text":
                texts.append(block.text)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return "\n".join(texts), seen_urls


def parse_json(text):
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    raw = blocks[-1] if blocks else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def validate(items, ind, seen_urls, start, end):
    ids = {c["id"] for c in ind["companies"]}
    ok = []
    for n in items:
        try:
            d = datetime.date.fromisoformat(n["date"])
        except Exception:
            continue
        if not (start - datetime.timedelta(days=1) <= d <= end):
            continue
        n["companies"] = [c for c in n.get("companies", []) if c.get("id") in ids and c.get("dir") in (1, -1)]
        n["sources"] = [s for s in n.get("sources", []) if s.get("url") in seen_urls]
        if not n["companies"] or not n["sources"]:
            continue  # 会社か出典が確認できないものは捨てる
        n["title"] = str(n.get("title", ""))[:30]
        n["summary"] = str(n.get("summary", ""))
        n["tags"] = [str(t) for t in n.get("tags", [])][:3]
        if n.get("confidence") not in ("公式発表", "報道", "統計"):
            n["confidence"] = "報道"
        ok.append(n)
    return ok


def update_industry(ind_id, today):
    path = f"{ind_id}.json"
    with open(path, encoding="utf-8") as f:
        ind = json.load(f)
    end = today - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=6)

    text, urls = run_claude(build_prompt(ind, start, end))
    try:
        items = parse_json(text).get("news", [])
    except Exception as e:
        print(f"[{ind_id}] JSONを読み取れませんでした: {e}")
        return False
    new = validate(items, ind, urls, start, end)
    print(f"[{ind_id}] 候補{len(items)}件 → 採用{len(new)}件（検索で見たURL {len(urls)}件）")
    if not new:
        print(f"[{ind_id}] 採用できるニュースがなかったので、今週は更新しません")
        return False

    os.makedirs("archive", exist_ok=True)
    with open(f"archive/{ind_id}-{ind.get('updated','old')}.json", "w", encoding="utf-8") as f:
        json.dump(ind, f, ensure_ascii=False, indent=2)

    stamp = today.strftime("%Y%m%d")
    for i, n in enumerate(new, 1):
        n["id"] = f"{stamp}-{i}"
    keep = [n for n in ind["news"] if n.get("ongoing")]
    ind["news"] = new + keep
    ind["period"] = f"{jp_date(start)}〜{end.month}月{end.day}日"
    ind["updated"] = today.isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ind, f, ensure_ascii=False, indent=2)
    return True


def main():
    today = datetime.datetime.now(JST).date()
    only = sys.argv[1:]  # 例：python update_news.py auto で自動車だけ
    with open("industries.json", encoding="utf-8") as f:
        inds = [i["id"] for i in json.load(f)["industries"]]
    changed = False
    for ind_id in inds:
        if only and ind_id not in only:
            continue
        try:
            changed |= update_industry(ind_id, today)
        except Exception as e:
            print(f"[{ind_id}] エラー: {e}")
    print("更新あり" if changed else "更新なし")


if __name__ == "__main__":
    main()
```

リポジトリのトップに「update_news.py」が並べば完了です。次のステップ5（定期実行の設定ファイル）も同じ貼り付け方式でいきます。
