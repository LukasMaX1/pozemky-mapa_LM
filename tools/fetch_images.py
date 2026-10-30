"""Stiahne hlavné fotky inzerátov a uloží ich do out/img/<id>.jpg + out/manifest.json.
Zdroj: imageUrl z data.json, inak og:image z detailu inzerátu (len ak robots.txt povoľuje).
Vetva img-cache slúži na prenos fotiek do aplikácie a pre mapu."""
import json, os, io, re, hashlib, requests
from urllib.parse import urlparse, urljoin
from urllib import robotparser
from PIL import Image
UA = "Mozilla/5.0 (Linux; Android 14) pozemky-mapa/1.0 (osobne pouzitie)"
H = {"User-Agent": UA, "Accept-Language": "sk"}
d = json.load(open("data.json"))
os.makedirs("out/img", exist_ok=True)
old = {}
try:
    old = json.load(open("prev_manifest.json"))
except Exception:
    pass
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
BAD = re.compile(r"(/_next/static/media/|logo|placeholder|OG-|og-default|banner)", re.I)
def og_image(page):
    if "bazos." in page or not allowed(page):
        return None
    r = requests.get(page, headers=H, timeout=20)
    if not r.ok:
        return None
    for pat in [r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image']:
        m = re.search(pat, r.text, re.I)
        if m:
            u = urljoin(page, m.group(1).replace("&amp;", "&"))
            if not BAD.search(u):
                return u
    m = re.search(r'https://img\.nehnutelnosti\.sk/[^"\'\s>]+\.(?:jpe?g|webp)', r.text)
    return m.group(0) if m else None
man = {}
for p in d.get("plots", []):
    if p.get("gone"):
        continue
    src = p.get("imageUrl")
    if not src:
        for l in p.get("links", []):
            u = l.get("url", "")
            if u.startswith("https://") and "bazos." not in u and "/vysledky/" not in u:
                try:
                    src = og_image(u)
                except Exception as e:
                    print("page fail", p["id"], e)
                if src:
                    break
    if not src or not src.startswith("https://"):
        continue
    try:
        r = requests.get(src, headers=H, timeout=20)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        if min(im.size) < 120:
            continue
        im.thumbnail((720, 720))
        b = io.BytesIO(); im.save(b, "JPEG", quality=78, optimize=True)
        open(f"out/img/{p['id']}.jpg", "wb").write(b.getvalue())
        man[p["id"]] = {"src": src, "sha": hashlib.sha1(b.getvalue()).hexdigest()[:12]}
    except Exception as e:
        print("skip", p["id"], e)
json.dump(man, open("out/manifest.json", "w"), indent=1)
print(len(man), "images")
