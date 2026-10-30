"""Overí každý pozemok podľa detailu inzerátu na portáli a vyčíta z neho dôležité údaje.
Výstup: out/verify.json  {id: {...}}  – používa ho fetch_images.py (vlastná galéria inzerátu)
a denná synchronizácia (oprava výmery/ceny, zrušené inzeráty, siete, rozmery, parcela …).
Bazoš sa nesťahuje (zákaz v robots.txt) – také pozemky ostávajú „neoverené“."""
import datetime
import json
import os
import sys
from urllib import robotparser
from urllib.parse import urlparse

import time

import requests

sys.path.insert(0, os.path.dirname(__file__))
from extract import GAL_RE, extract, merge_area, parse_page  # noqa: E402

UA = "Mozilla/5.0 (Linux; Android 14) pozemky-mapa/1.0 (osobne pouzitie)"
H = {"User-Agent": UA, "Accept-Language": "sk"}
robots = {}


def allowed(u):
    host = urlparse(u).scheme + "://" + urlparse(u).netloc
    if host not in robots:
        rp = robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers=H, timeout=10)
            rp.parse(r.text.splitlines() if r.ok else [])
        except Exception:
            rp.parse([])
        robots[host] = rp
    return robots[host].can_fetch(UA, u)


def link_kind(u):
    if not u.startswith("https://"):
        return "bad"
    if "bazos." in u:
        return "bazos"
    if "/vysledky/" in u or "/hladanie" in u or "/search" in u:
        return "search"
    if "nehnutelnosti.sk/detail/" in u:
        return "nehn"
    return "other"


def check_link(u, cache):
    kind = link_kind(u)
    res = {"url": u, "kind": kind}
    if kind in ("bad", "bazos", "search"):
        res["state"] = {"bad": "chybný", "bazos": "neoveriteľný", "search": "vyhľadávanie"}[kind]
        return res
    if not allowed(u):
        res["state"] = "robots"
        return res
    if u in cache:
        return dict(cache[u])
    r, err = None, None
    for wait in (0, 4, 12, 30):
        time.sleep(wait or 0.7)  # šetrné tempo, pri chybe servera opakovať
        try:
            r = requests.get(u, headers=H, timeout=25, allow_redirects=True)
            err = None
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:120]
    if r is None or err:
        res["state"] = "chyba"
        res["error"] = err or "bez odpovede"
        return res
    res["final"] = r.url
    if r.status_code in (404, 410) or (kind == "nehn" and "/detail/" not in r.url):
        res["state"] = "zrušený"
    elif not r.ok:
        res["state"] = "chyba"
        res["error"] = f"HTTP {r.status_code}"
    else:
        pg = parse_page(r.text)
        if not pg.get("title"):
            res["state"] = "neprečítaný" if kind == "other" else "zrušený"
        else:
            ex = extract(pg.get("title"), pg.get("desc"))
            res.update(state="ok", title=pg.get("title"), area=merge_area(pg, ex), price=pg.get("price") or None,
                       agent=pg.get("agent"), published=pg.get("published"), modified=pg.get("modified"),
                       canonical=(pg.get("canonical") or r.url).split("?")[0], images=pg.get("images", []),
                       extract={k: v for k, v in ex.items() if k != "titleArea"}, desc=(pg.get("descText") or pg.get("desc") or "")[:8000])
            if res["price"] is not None and res["price"] < 100:
                res["price"] = None  # 0 / 1 € = cena dohodou
    cache[u] = res
    return dict(res)


def norm(u):
    return u.split("?")[0].split("#")[0].rstrip("/")


def main():
    d = json.load(open("data.json"))
    os.makedirs("out", exist_ok=True)
    cache, out, canon_owner = {}, {}, {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for p in d.get("plots", []):
        pid = p["id"]
        seen, links = set(), []
        for l in p.get("links", []):
            u = norm(l.get("url", ""))
            if not u or u in seen:
                continue
            seen.add(u)
            r = check_link(l.get("url", ""), cache)
            r["portal"] = l.get("portal")
            links.append(r)
        ok = [l for l in links if l["state"] == "ok"]
        issues, data = [], {}
        if ok:
            best = ok[0]
            for l in ok:
                for k, v in l["extract"].items():
                    if k == "utilities":
                        data.setdefault("utilities", {}).update({a: b for a, b in v.items() if a not in data.get("utilities", {})})
                    elif k == "utilDetail":
                        data.setdefault("utilDetail", {}).update({a: b for a, b in v.items() if a not in data.get("utilDetail", {})})
                    elif k not in data:
                        data[k] = v
            data["area"] = best.get("area")
            data["price"] = next((l["price"] for l in ok if l.get("price")), None)
            data["agent"] = best.get("agent")
            data["published"] = min((l["published"] for l in ok if l.get("published")), default=None)
            data["modified"] = max((l["modified"] for l in ok if l.get("modified")), default=None)
            data["listingTitle"] = best.get("title")
            data["description"] = best.get("desc") or ""
            imgs, keys = [], set()
            for l in ok:
                for i in l.get("images", []):
                    m = GAL_RE.match(i)
                    key = m.group(1) if m else i.split("?")[0]
                    if key not in keys:
                        keys.add(key)
                        imgs.append(i)
            data["images"] = imgs
            areas = {round(l["area"]) for l in ok if l.get("area")}
            if len(areas) > 1:
                issues.append("odkazy uvádzajú rôzne výmery: " + ", ".join(f"{a} m²" for a in sorted(areas)))
            if p.get("area") and data.get("area") and abs(p["area"] - data["area"]) > 5:
                issues.append(f"výmera opravená {p['area']} → {data['area']:g} m²")
            if p.get("price") and data.get("price") and abs(p["price"] - data["price"]) > 100:
                issues.append(f"cena podľa inzerátu {data['price']:,.0f} € (bolo {p['price']:,.0f} €)".replace(",", " "))
            status = "overený"
            for l in ok:
                c = l.get("canonical")
                if c:
                    if c in canon_owner and canon_owner[c] != pid:
                        issues.append(f"rovnaký inzerát ako {canon_owner[c]}")
                    canon_owner.setdefault(c, pid)
        elif any(l["state"] == "zrušený" for l in links):
            status = "zrušený"
            issues.append("inzerát už na portáli nie je")
        elif any(l["state"] == "neoveriteľný" for l in links):
            status = "neoverený"
            issues.append("len Bazoš – údaje neoverené z detailu")
        elif any(l["state"] in ("chyba", "robots", "neprečítaný") for l in links):
            status = "neoverený"
            issues.append("detail sa nepodarilo načítať")
        else:
            status = "chybný"
            issues.append("žiadny odkaz nevedie na konkrétny inzerát")
        bad = [l["url"] for l in links if l["state"] in ("vyhľadávanie", "chybný")]
        if bad:
            issues.append(f"odstránené odkazy na vyhľadávanie: {len(bad)}")
        dup = len(p.get("links", [])) - len(links)
        out[pid] = {
            "checked": now,
            "status": status,
            "issues": issues,
            "data": data,
            "links": [{k: l.get(k) for k in ("url", "portal", "state", "final", "canonical", "area", "price", "title", "agent", "published", "modified", "error")} for l in links if l["state"] not in ("vyhľadávanie", "chybný")],
            "removedLinks": bad,
            "dupLinks": dup,
        }
    json.dump(out, open("out/verify.json", "w"), ensure_ascii=False, indent=1)
    c = {}
    for v in out.values():
        c[v["status"]] = c.get(v["status"], 0) + 1
    print("verify:", c)


if __name__ == "__main__":
    main()
