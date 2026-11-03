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


MW, MH, PADX, PADY, ZMIN = 240, 240, 30, 30, 11  # rozmer mini-mapy v aplikácii (CSS px) a okraje


class Tiles:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.c = {}
        self.n = 0

    def get(self, z, x, y):
        k = (z, x, y)
        if k not in self.c:
            im = None
            for _ in range(3):
                try:
                    r = self.s.get(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png", timeout=20)
                    if r.ok:
                        im = Image.open(io.BytesIO(r.content)).convert("RGB")
                        self.n += 1
                        break
                except Exception:
                    pass
                time.sleep(2)
            time.sleep(0.25)
            self.c[k] = im
        return self.c[k]


def wpx(lat, lng, z):
    x, y = tile_xy(lat, lng, z)
    return x * 256, y * 256


def minimaps(d, o, man, T):
    """Ostrá mini-mapa pre každý aktívny pozemok: pozemok + referenčné miesto, 2× rozlíšenie."""
    made = reused = 0
    for p in d.get("plots", []):
        if p.get("invalid") or p.get("gone") or p.get("lat") is None or p.get("rating") in ("hide", "no"):
            continue
        z = 15
        while z > ZMIN:
            ax, ay = wpx(p["lat"], p["lng"], z)
            bx, by = wpx(o[0], o[1], z)
            if abs(ax - bx) <= MW - 2 * PADX and abs(ay - by) <= MH - 2 * PADY:
                break
            z -= 1
        ax, ay = wpx(p["lat"], p["lng"], z)
        bx, by = wpx(o[0], o[1], z)
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        # ak sa referenčné miesto nezmestí, pozemok ostane v zábere a čiara vedie mimo okraj
        cx = min(max(cx, ax - (MW / 2 - PADX)), ax + (MW / 2 - PADX))
        cy = min(max(cy, ay - (MH / 2 - PADY)), ay + (MH / 2 - PADY))
        cx, cy = round(cx), round(cy)
        name = f"mm2-{p['id']}-z{z}-x{cx}-y{cy}.jpg"
        dst = os.path.join("out/img", name)
        prev = os.path.join("prev/img", name)
        if os.path.exists(prev):
            shutil.copy(prev, dst)
            reused += 1
        else:
            Z2 = z + 1
            X0, Y0 = cx * 2 - MW, cy * 2 - MH  # ľavý horný roh v pixeloch na zoome z+1
            img = Image.new("RGB", (MW * 2, MH * 2), (238, 238, 232))
            ok = 0
            for tx in range(X0 // 256, (X0 + MW * 2) // 256 + 1):
                for ty in range(Y0 // 256, (Y0 + MH * 2) // 256 + 1):
                    t = T.get(Z2, tx, ty)
                    if t is not None:
                        img.paste(t, (tx * 256 - X0, ty * 256 - Y0))
                        ok += 1
            if not ok:
                continue
            img.save(dst, "JPEG", quality=74, optimize=True, progressive=True)
            made += 1
        sha = hashlib.sha1(open(dst, "rb").read()).hexdigest()[:12]
        man["_mm:" + p["id"]] = {"sha": sha, "photos": [{"file": name, "sha": sha}]}
    print("mini-mapy:", made, "nových,", reused, "z cache")


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
    try:
        minimaps(d, pts[0], m, Tiles())
    except Exception as e:
        print("mini-mapy: chyba", e)
    json.dump(m, open(mp, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
