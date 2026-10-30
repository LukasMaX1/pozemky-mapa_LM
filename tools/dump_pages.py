"""Diagnostika: stiahne HTML detailov inzerátov (nie Bazoš, len ak robots.txt povoľuje) do out/html/<id>__<n>.html.gz"""
import json, os, gzip, requests
from urllib.parse import urlparse
from urllib import robotparser
UA = "Mozilla/5.0 (Linux; Android 14) pozemky-mapa/1.0 (osobne pouzitie)"
H = {"User-Agent": UA, "Accept-Language": "sk"}
d = json.load(open("data.json"))
os.makedirs("out/html", exist_ok=True)
rp = {}
def ok(u):
    h = urlparse(u).scheme + "://" + urlparse(u).netloc
    if h not in rp:
        r = robotparser.RobotFileParser()
        try:
            t = requests.get(h + "/robots.txt", headers=H, timeout=10)
            r.parse(t.text.splitlines() if t.ok else [])
        except Exception:
            r.parse([])
        rp[h] = r
    return rp[h].can_fetch(UA, u)
log = {}
for p in d["plots"]:
    seen = set()
    for i, l in enumerate(p.get("links", [])):
        u = l.get("url", "")
        if not u.startswith("https://") or "bazos." in u or u in seen:
            continue
        seen.add(u)
        if not ok(u):
            log[f"{p['id']}__{i}"] = {"url": u, "status": "robots"}
            continue
        try:
            r = requests.get(u, headers=H, timeout=25, allow_redirects=True)
            log[f"{p['id']}__{i}"] = {"url": u, "status": r.status_code, "final": r.url, "len": len(r.text)}
            gzip.open(f"out/html/{p['id']}__{i}.html.gz", "wt", encoding="utf-8").write(r.text)
        except Exception as e:
            log[f"{p['id']}__{i}"] = {"url": u, "status": str(e)}
json.dump(log, open("out/html/log.json", "w"), indent=1)
print(len(log))
