"""Súradnice obcí cez OpenStreetMap Nominatim (max 1 dotaz/s, výsledky v cache).
Používa verify_listings.py na kontrolu polohy pozemku."""
import json
import math
import os
import time
import unicodedata

import requests

UA = "pozemky-mapa/1.0 (+https://github.com/LukasMaX1/pozemky-mapa_LM)"
CACHE_IN = "prev/geo.json"
CACHE_OUT = "out/geo.json"
_cache = None
_last = 0.0


def _key(v):
    s = unicodedata.normalize("NFKD", (v or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _load():
    global _cache
    if _cache is None:
        try:
            _cache = json.load(open(CACHE_IN))
        except Exception:
            _cache = {}
    return _cache


def save():
    os.makedirs("out", exist_ok=True)
    json.dump(_load(), open(CACHE_OUT, "w"), ensure_ascii=False, indent=1)


def village(name):
    """[lat, lng] stredu obce (alebo mestskej časti Košíc), None ak sa nenašla."""
    global _last
    c = _load()
    k = _key(name)
    if not k:
        return None
    if k in c:
        return c[k]
    res = None
    queries = [f"{name}, okres Košice-okolie", f"{name}, Košický kraj", f"{name}, Prešovský kraj", f"Košice-{name}" if not name.lower().startswith("košice") else name]
    for q in queries:
        wait = 1.1 - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search", params={"q": q, "format": "json", "limit": 1, "countrycodes": "sk", "accept-language": "sk"}, headers={"User-Agent": UA}, timeout=20)
            j = r.json() if r.ok else []
        except Exception:
            j = []
        if j:
            res = [round(float(j[0]["lat"]), 6), round(float(j[0]["lon"]), 6)]
            break
    c[k] = res
    return res


def km(a, b):
    if not a or not b:
        return None
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 73.4)
