"""Zapracuje out/verify.json do záznamov pozemkov.
Použitie: python3 tools/apply_verify.py <plots_dir> <verify.json> <out_dir>
Do <out_dir> zapíše len zmenené pozemky (celý dokument) + changes.txt so zoznamom zmien.
Údaje z detailu inzerátu majú prednosť pred údajmi z vyhľadávania (snippetov)."""
import datetime
import json
import os
import sys

FILL = ["shape", "access", "street", "permit", "project", "zoning", "landType", "upOk", "dimsNote", "multi", "flood"]


def main(plots_dir, ver_path, out_dir):
    ver = json.load(open(ver_path))
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()
    log = []
    for f in sorted(os.listdir(plots_dir)):
        if not f.endswith(".json"):
            continue
        raw = json.load(open(os.path.join(plots_dir, f)))
        p = raw.get("data", raw) if isinstance(raw.get("data"), dict) else raw
        pid = f[:-5]
        v = ver.get(pid)
        if not v:
            continue
        before = json.dumps(p, sort_keys=True, ensure_ascii=False)
        ch = []
        d = v.get("data") or {}
        st = v["status"]
        # odkazy: bez vyhľadávaní a duplicít
        keep = {l["url"].split("?")[0].rstrip("/") for l in v.get("links", []) if not (st == "overený" and l.get("state") == "zrušený")}
        links, seen = [], set()
        for l in p.get("links", []):
            u = (l.get("url") or "").split("?")[0].split("#")[0].rstrip("/")
            if u in seen or u not in keep:
                continue
            seen.add(u)
            links.append(l)
        if len(links) != len(p.get("links", [])):
            ch.append(f"odkazy {len(p.get('links', []))}→{len(links)}")
            p["links"] = links
        if st == "zrušený" and not p.get("gone"):
            p["gone"] = True
            p["goneReason"] = "inzerát stiahnutý z portálu"
            p["goneAt"] = today
            ch.append("zrušený")
        if st == "chybný" and not p.get("invalid"):
            p["invalid"] = True
            p["invalidReason"] = "; ".join(v["issues"]) or "chybné údaje"
            ch.append("chybný")
        if st == "overený":
            if p.get("gone") and p.get("goneReason") == "inzerát stiahnutý z portálu":
                p["gone"] = False
                p.pop("goneReason", None)
                ch.append("znovu aktívny")
            a = d.get("area")
            if a and (not p.get("area") or abs(p["area"] - a) > 5):
                ch.append(f"výmera {p.get('area')}→{a:g}")
                p["area"] = round(a)
            pr = d.get("price")
            if pr and (not p.get("price") or abs(p["price"] - pr) > 100):
                ch.append(f"cena {p.get('price')}→{pr:g}")
                p["price"] = round(pr)
                h = p.setdefault("priceHistory", [])
                if not h or h[-1].get("price") != p["price"]:
                    h.append({"date": today, "price": p["price"]})
            if d.get("width") and d.get("length"):
                if (p.get("width"), p.get("length")) != (d["width"], d["length"]):
                    ch.append(f"rozmery {d['width']:g}×{d['length']:g}")
                p["width"], p["length"] = d["width"], d["length"]
            if d.get("terrain") and p.get("terrain") != d["terrain"]:
                ch.append(f"terén {p.get('terrain')}→{d['terrain']}")
                p["terrain"] = d["terrain"]
            if d.get("utilities"):
                u = dict(p.get("utilities") or {})
                u.update(d["utilities"])
                if u != (p.get("utilities") or {}):
                    ch.append("siete")
                p["utilities"] = u
                p["utilDetail"] = d.get("utilDetail") or {}
            if d.get("parcel") and not p.get("parcel"):
                p["parcel"] = d["parcel"]
                ch.append("parcela " + d["parcel"])
            if d.get("mainRoad") is not None and p.get("mainRoad") is None:
                p["mainRoad"] = d["mainRoad"]
            for k in FILL:
                if d.get(k) is not None and p.get(k) != d[k]:
                    p[k] = d[k]
            if d.get("category") in ("rekreacny", "nestavebny") and p.get("category") == "stavebny":
                ch.append("kategória → " + d["category"])
                p["category"] = d["category"]
            if d.get("reserved") and not p.get("reserved"):
                p["reserved"] = True
                ch.append("rezervovaný")
            fp = d.get("firstPublished")
            if fp and (not p.get("firstPublished") or fp < p["firstPublished"]):
                p["firstPublished"] = fp
            for k in ("kind", "kindNote"):
                if d.get(k) and p.get(k) != d[k]:
                    p[k] = d[k]
            if d.get("description"):
                p["description"] = d["description"][:6000]
            for k in ("agent", "published", "listingTitle"):
                if d.get(k):
                    p[k] = d[k]
        prev = p.get("check") or {}
        if st == "neoverený" and prev.get("status") == "overený" and any(l.get("state") == "chyba" for l in v.get("links", [])):
            # dočasná chyba portálu: ponechať poslednú úspešnú kontrolu
            p["check"] = dict(prev, lastError=v["checked"][:10])
            if json.dumps(p, sort_keys=True, ensure_ascii=False) != before:
                json.dump(p, open(os.path.join(out_dir, f), "w"), ensure_ascii=False, indent=1)
            continue
        # poloha: GPS z inzerátu, ak sedí s obcou; inak stred obce (OpenStreetMap)
        loc = v.get("loc") or {}
        vg, pg = loc.get("villageGps"), d.get("pageGps")
        new = None
        if pg and vg and (loc.get("pageDistKm") or 0) <= 4:
            new, prec, src = pg, True, "inzerát (±200 m)"
        elif vg:
            new, prec, src = vg, False, "stred obce"
        if new and not p.get("manualLoc"):
            old = [p.get("lat"), p.get("lng")]
            moved = old[0] is None or abs(old[0] - new[0]) > 0.003 or abs(old[1] - new[1]) > 0.004
            if moved:
                if old[0] is not None:
                    ch.append(f"poloha posunutá o {((old[0]-new[0])**2*12365+(old[1]-new[1])**2*5388)**0.5:.1f} km")
                p["lat"], p["lng"] = new
            p["precise"] = prec
            p["locSource"] = src
        p["check"] = {"status": st, "at": v["checked"][:10], "issues": v.get("issues", []), "photos": len(d.get("images") or [])}
        if json.dumps(p, sort_keys=True, ensure_ascii=False) != before:
            json.dump(p, open(os.path.join(out_dir, f), "w"), ensure_ascii=False, indent=1)
            if ch:
                log.append(f"{pid}: " + ", ".join(ch))
    open(os.path.join(out_dir, "changes.txt"), "w").write("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main(*sys.argv[1:4])
