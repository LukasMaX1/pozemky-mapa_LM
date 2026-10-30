"""Stiahne hlavné fotky inzerátov (imageUrl z data.json), zmenší ich a uloží do out/img/<id>.jpg
spolu s out/manifest.json. Vetva img-cache slúži len ako dočasný prenos do aplikácie."""
import json, os, io, hashlib, requests
from PIL import Image
d = json.load(open("data.json"))
os.makedirs("out/img", exist_ok=True)
man = {}
H = {"User-Agent": "Mozilla/5.0 (pozemky-mapa; osobné použitie)"}
for p in d.get("plots", []):
    u = p.get("imageUrl")
    if not u or p.get("gone") or not u.startswith("https://"):
        continue
    try:
        r = requests.get(u, headers=H, timeout=20)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((720, 720))
        b = io.BytesIO(); im.save(b, "JPEG", quality=78, optimize=True)
        open(f"out/img/{p['id']}.jpg", "wb").write(b.getvalue())
        man[p["id"]] = {"src": u, "sha": hashlib.sha1(b.getvalue()).hexdigest()[:12]}
    except Exception as e:
        print("skip", p["id"], e)
json.dump(man, open("out/manifest.json", "w"), indent=1)
print(len(man), "images")
