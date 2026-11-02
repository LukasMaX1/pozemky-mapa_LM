"""Podkladová mapa pre mini-mapy v kartách aplikácie.
Zloží jeden obrázok z dlaždíc OpenStreetMap (zoom 12) pokrývajúci všetky pozemky a referenčné miesto.
Rozsah je zakódovaný v názve súboru: out/img/basemap-z12-x<tx>-y<ty>.jpg (ľavá horná dlaždica).
Dlaždice sa sťahujú len vtedy, keď sa rozsah zmení (inak sa použije včerajší obrázok z prev/).
Zapíše položku "_basemap" do out/manifest.json."""
import glob
import hashlib
import io
import json
import math
import os
import shutil
import time

import requests
from PIL import Image

Z = 12
PAD_KM = 4
UA = "pozemky-mapa/1.0 (osobne pouzitie; https://github.com/LukasMaX1/pozemky-mapa_LM)"
CENTER = (48.7206, 21.2575)


def tile_xy(lat, lng, z=Z):
    n = 2 ** z
    x = (lng + 180) / 360 * n
    r = math.radians(lat)
    y = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
    return x, y


def main():
    d = json.load(open("data.json"))
    o = (d.get("settings") or {}).get("origin") or {}
    pts = [(o["lat"], o["lng"]) if isinstance(o.get("lat"), (int, float)) else CENTER]
    for p in d.get("plots", []):
        if p.get("invalid") or p.get("lat") is None:
            continue
        # len rozumná oblasť (do ~70 km od Košíc)
        if abs(p["lat"] - CENTER[0]) > 0.65 or abs(p["lng"] - CENTER[1]) > 0.95:
            continue
        pts.append((p["lat"], p["lng"]))
    dl, dg = PAD_KM / 111.2, PAD_KM / 73.4
    la0, la1 = min(a for a, _ in pts) - dl, max(a for a, _ in pts) + dl
    lg0, lg1 = min(b for _, b in pts) - dg, max(b for _, b in pts) + dg
    x0, y0 = (int(v) for v in tile_xy(la1, lg0))
    x1, y1 = (int(v) for v in tile_xy(la0, lg1))
    name = f"basemap-z{Z}-x{x0}-y{y0}-w{x1 - x0 + 1}-h{y1 - y0 + 1}.jpg"
    os.makedirs("out/img", exist_ok=True)
    dst = os.path.join("out/img", name)
    prev = os.path.join("prev/img", name)
    if os.path.exists(prev):
        shutil.copy(prev, dst)
        print("basemap: bez zmeny", name)
    else:
        img = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (238, 238, 232))
        s = requests.Session()
        s.headers["User-Agent"] = UA
        n = 0
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                for attempt in range(3):
                    try:
                        r = s.get(f"https://tile.openstreetmap.org/{Z}/{tx}/{ty}.png", timeout=20)
                        if r.ok:
                            img.paste(Image.open(io.BytesIO(r.content)).convert("RGB"), ((tx - x0) * 256, (ty - y0) * 256))
                            n += 1
                            break
                    except Exception:
                        pass
                    time.sleep(2)
                time.sleep(0.25)
        if n == 0:
            print("basemap: dlaždice sa nepodarilo stiahnuť")
            old = sorted(glob.glob("prev/img/basemap-*.jpg"))
            if not old:
                return
            name = os.path.basename(old[-1])
            dst = os.path.join("out/img", name)
            shutil.copy(old[-1], dst)
        else:
            img.save(dst, "JPEG", quality=72, optimize=True, progressive=True)
            print("basemap:", name, n, "dlaždíc", os.path.getsize(dst) // 1024, "kB")
    sha = hashlib.sha1(open(dst, "rb").read()).hexdigest()[:12]
    mp = "out/manifest.json"
    m = json.load(open(mp)) if os.path.exists(mp) else {}
    m["_basemap"] = {"sha": sha, "photos": [{"file": name, "sha": sha}]}
    json.dump(m, open(mp, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
