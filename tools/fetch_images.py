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
GAL = re.compile(r'https://img\.unitedclassifieds\.sk/foto/[A-Za-z0-9_\-]+/([A-Za-z0-9_\-]+?)_(\w+)\?[^"\'\s<>\\]+')
MAXP = 8
def page_photos(page):
    """Vráti zoznam URL fotiek inzerátu (najprv og:image, potom galéria), bez duplicít."""
    if "bazos." in page or not allowed(page):
        return []
    r = requests.get(page, headers=H, timeout=20)
    if not r.ok:
        return []
    html = r.text.replace("\\u0026", "&").replace("&amp;", "&")
    out, seen = [], set()
    def add(u, key):
        if key in seen or BAD.search(u):
            return
        seen.add(key); out.append(u)
    for pat in [r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image']:
        m = re.search(pat, html, re.I)
        if m:
            u = urljoin(page, m.group(1)); g = GAL.search(u)
            add(u, g.group(1) if g else u)
            break
    best = {}
    for m in GAL.finditer(html):
        pid, size = m.group(1), m.group(2)
        if pid not in best or size == "fss":
            best[pid] = m.group(0)
    for pid, u in best.items():
        add(u, pid)
    return out[:MAXP]
def save(u, path):
    r = requests.get(u, headers=H, timeout=20)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    if min(im.size) < 120:
        return None
    im.thumbnail((960, 960))
    b = io.BytesIO(); im.save(b, "JPEG", quality=76, optimize=True)
    open(path, "wb").write(b.getvalue())
    return hashlib.sha1(b.getvalue()).hexdigest()[:12]
man = {}
for p in d.get("plots", []):
    if p.get("gone"):
        continue
    urls = []
    for l in p.get("links", []):
        u = l.get("url", "")
        if u.startswith("https://") and "bazos." not in u and "/vysledky/" not in u:
            try:
                urls = page_photos(u)
            except Exception as e:
                print("page fail", p["id"], e)
            if urls:
                break
    if not urls and p.get("imageUrl", "").startswith("https://"):
        urls = [p["imageUrl"]]
    photos = []
    for i, u in enumerate(urls):
        fn = f"{p['id']}.jpg" if i == 0 else f"{p['id']}-{i+1}.jpg"
        try:
            sha = save(u, f"out/img/{fn}")
            if sha:
                photos.append({"file": fn, "sha": sha})
        except Exception as e:
            print("skip", p["id"], i, e)
    if photos:
        man[p["id"]] = {"sha": photos[0]["sha"], "photos": photos}
json.dump(man, open("out/manifest.json", "w"), indent=1)
print(len(man), "images")
