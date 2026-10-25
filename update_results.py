#!/usr/bin/env python3
"""バレー日程アプリの結果を自動更新する。
 ・SVリーグ（東京GB）: 公式の日程ページから終了試合のセットスコアを取得
 ・日本代表: スポーツナビの大会ページから終了試合を取得
終わった試合のうち、まだスコアが入っていないものがある月／大会だけを見に行く。
変更がなければ index.html に触れない。標準ライブラリのみ。"""
import json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

HERE = sys.argv[1] if len(sys.argv) > 1 else "."
CONF = json.load(open(f"{HERE}/update_config.json", encoding="utf-8"))
HTML = f"{HERE}/index.html"
UA = {"User-Agent": "Mozilla/5.0"}

def fetch(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            if i == 2: raise
            time.sleep(3)

# ---------- SVリーグ ----------
def sv_results(months):
    base = CONF["sv"]["base"]; tid = CONF["sv"]["tid"]; me = CONF["sv"]["team"]; season = CONF["sv"]["season"]
    found = {}
    for y, mo in months:
        h = fetch(f"{base}?s={season}&y={y}&m={mo}&t={tid}")
        for d in sorted(set(int(x) for x in re.findall(r'id="div_day_(\d+)"', h))):
            hd = fetch(f"{base}?s={season}&y={y}&m={mo}&d={d}&t={tid}")
            ml = re.search(r'<dl class="match-list reset" id="match-list">(.*?)</dl>', hd, re.S)
            if not ml: continue
            for dt, dd in re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', ml.group(1), re.S):
                sides = re.findall(r'<li class="[^"]*">\s*<em>(?:HOME|AWAY)</em>.*?<b>([^<]*)</b>\s*<div class="game">(.*?)</div>', dd, re.S)
                if len(sides) < 2: continue
                names = [t[0].strip() for t in sides]
                if me not in names: continue
                vals = [[x.strip() for x in re.findall(r'<span[^>]*>(.*?)</span>', t[1], re.S)] for t in sides]
                if not any(vals[0]) or not vals[0][-1]: continue        # 未実施
                mid = re.search(r'/match/detail/(\d+)/', dd)
                if not mid: continue
                i = names.index(me); a, b = vals[i], vals[1 - i]
                ms, os_ = int(a[-1]), int(b[-1])
                found[mid.group(1)] = {
                    "sc": f"{ms}-{os_}",
                    "r": "W" if ms > os_ else ("L" if ms < os_ else "D"),
                    "ss": "・".join(f"{x}-{y}" for x, y in zip(a[:-1], b[:-1]) if x and y)}
            time.sleep(0.3)
    return found

# ---------- 日本代表（スポーツナビ） ----------
def nt_results(cid):
    base = CONF["nt"]["base"].format(cid=cid)
    h = fetch(base); out = {}
    for d in sorted(set(re.findall(r'schedule\?date=(\d{8})', h))):
        for tr in re.findall(r'<tr class="vb-tableGame__row">(.*?)</tr>', fetch(f"{base}?date={d}"), re.S):
            if "日本" not in tr: continue
            dt = re.search(r'datetime="([^"]+)"', tr)
            sides = []
            for side in ("home", "away"):
                blk = re.search(rf'<div class="vb-tableGame__{side}">(.*?)(?=<div class="vb-tableGame__(?:away|status)|<a class="vb-tableGame__status")', tr, re.S)
                seg = blk.group(1) if blk else ""
                team = re.search(r'vb-tableGame__team">([^<]*)<', seg)
                res = re.search(r'vb-tableGame__result">([^<]*)<', seg)
                sides.append({"team": team.group(1).strip() if team else "",
                              "sets": res.group(1).strip() if res else "",
                              "pts": re.findall(r'vb-tableGame__point">([^<]*)<', seg)})
            a, b = sides
            if not a["sets"] or not b["sets"] or not dt: continue
            me, op = (a, b) if a["team"] == "日本" else (b, a)
            ms, os_ = int(me["sets"]), int(op["sets"])
            out[dt.group(1)[:10]] = {"sc": f"{ms}-{os_}", "r": "W" if ms > os_ else "L",
                                     "ss": "・".join(f"{x}-{y}" for x, y in zip(me["pts"], op["pts"])),
                                     "opp": op["team"]}
        time.sleep(0.3)
    return out

html = open(HTML, encoding="utf-8").read()
m = re.search(r'const DATA=(\{.*?\});\n', html, re.S)
DATA = json.loads(m.group(1))
today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
changes = []

sv_tab = CONF["sv"]["tab"]
pending = [g for g in DATA[sv_tab]["games"] if g["d"] <= today and not g["sc"] and g.get("id")]
if pending:
    months = sorted({(int(g["d"][:4]), int(g["d"][5:7])) for g in pending})
    res = sv_results(months)
    for g in DATA[sv_tab]["games"]:
        r = res.get(g.get("id") or "")
        if r and g["sc"] != r["sc"]:
            g.update(sc=r["sc"], r=r["r"], ss=r["ss"])
            changes.append(f'{DATA[sv_tab]["short"]} {g["d"]} vs {g["opp"]}: '
                           f'{"○" if r["r"]=="W" else "●" if r["r"]=="L" else "△"} {r["sc"]}')

for tab, cids in CONF["nt"]["tabs"].items():
    if tab not in DATA: continue
    pend = [g for g in DATA[tab]["games"] if g["d"] <= today and not g["sc"]]
    if not pend: continue
    for cid in cids:
        res = nt_results(cid)
        for g in DATA[tab]["games"]:
            r = res.get(g["d"])
            if r and g["sc"] != r["sc"]:
                g.update(sc=r["sc"], r=r["r"], ss=r["ss"])
                if g["opp"].startswith("（"): g["opp"] = r["opp"]
                changes.append(f'{DATA[tab]["short"]} {g["d"]} vs {g["opp"]}: '
                               f'{"○" if r["r"]=="W" else "●"} {r["sc"]}')

if not changes:
    print("変更なし"); sys.exit(0)
html = html[:m.start(1)] + json.dumps(DATA, ensure_ascii=False) + html[m.end(1):]
jst = datetime.now(timezone(timedelta(hours=9)))
html = re.sub(r'データ更新日：\d{4}年\d{1,2}月\d{1,2}日', f'データ更新日：{jst.year}年{jst.month}月{jst.day}日', html, count=1)
open(HTML, "w", encoding="utf-8").write(html)
print(f"{len(changes)}件の変更"); print("\n".join(changes))
