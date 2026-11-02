"""Overenie inzerátu z detailovej stránky a vyčítanie dôležitých údajov z textu.

parse_page(html)  -> údaje zo štruktúrovaných dát stránky (JSON-LD: výmera, cena, galéria, RK, dátumy)
extract(text)     -> údaje vyčítané z názvu a popisu (rozmery, siete, terén, parcela, druh pozemku …)
"""
import json
import re
import unicodedata

GAL_RE = re.compile(r"https://img\.unitedclassifieds\.sk/foto/[A-Za-z0-9_\-]+/([A-Za-z0-9_\-]+?)_\w+\?[^\"'\s<>\\]*")


def _num(s):
    if s is None:
        return None
    s = re.sub(r"[^\d,.]", "", str(s)).replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _strip(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", t).strip()


def _text(t):
    """Text inzerátu s odsekmi (pre zobrazenie celého popisu)."""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>", "\n", t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("\r", "")
    t = re.sub(r"(?<=[.!?…])[ \t\xa0]{2,}|[ \t\xa0]{2,}(?=[A-ZÁČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ•✔📍📐🌱📄✅➡▪-])", "\n", t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _flight_ad(html):
    """Údaje inzerátu z Next.js flight dát (dátum vytvorenia, text s odsekmi)."""
    parts = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try:
            parts.append(json.loads(m.group(1)))
        except Exception:
            pass
    pay = "".join(parts)
    i = pay.find('"advertisement":{')
    if i < 0:
        return None
    ad, _ = json.JSONDecoder().raw_decode(pay[i + len('"advertisement":'):])
    d = ad.get("description")
    if isinstance(d, str) and re.fullmatch(r"\$[0-9a-f]+", d):
        m = re.search(r"(?:^|\n)" + re.escape(d[1:]) + r":T([0-9a-f]+),", pay)
        if m:
            n = int(m.group(1), 16)
            raw = pay[m.end():].encode("utf-8")[:n].decode("utf-8", "ignore")
            ad["descText"] = _text(raw)
    elif isinstance(d, str):
        ad["descText"] = _text(d)
    return ad


def parse_page(html):
    out = {"images": []}
    for m in re.finditer(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        nodes = d.get("@graph", [d]) if isinstance(d, dict) else []
        for n in nodes:
            ty = n.get("@type")
            if ty == "Accommodation":
                out["ldArea"] = _num((n.get("floorSize") or {}).get("value"))
                out["ldCat"] = n.get("accommodationCategory")
            elif ty == "Offer":
                ps = n.get("priceSpecification") or {}
                out["price"] = _num(ps.get("price"))
                out["canonical"] = n.get("url")
                out["availability"] = (n.get("availability") or "").rsplit("/", 1)[-1]
            elif ty == "Product":
                out["title"] = _strip(n.get("name"))
                out["desc"] = _strip(n.get("description"))
                out["descText"] = _text(n.get("description"))
                imgs = []
                for i in n.get("image") or []:
                    u = i.get("@id") or i.get("contentUrl") or i.get("url") if isinstance(i, dict) else i
                    if isinstance(u, str) and u.startswith("https://") and u not in imgs:
                        imgs.append(u)
                out["images"] = imgs
            elif ty == "RealEstateAgent":
                out["agent"] = _strip(n.get("name"))
            elif ty == "ItemPage":
                out["published"] = (n.get("datePublished") or "")[:10] or None
                out["modified"] = (n.get("dateModified") or "")[:10] or None
    try:
        ad = _flight_ad(html)
    except Exception:
        ad = None
    if ad:
        out["createdAt"] = (ad.get("createdAt") or "")[:10] or None
        out["publishedAt"] = (ad.get("publishedAt") or "")[:10] or None
        out["updatedAt"] = (ad.get("updatedAt") or "")[:10] or None
        if ad.get("descText"):
            out["descText"] = ad["descText"]
        out["adKeys"] = sorted(k for k in ad.keys() if k != "descText")[:80]
        st = {k: v for k, v in ad.items() if re.search(r"view|visit|zobraz|stat|count|popular|impress|seen|click", k, re.I) and isinstance(v, (int, float, str, dict, list))}
        if st:
            out["adStats"] = json.loads(json.dumps(st)[:2000]) if len(json.dumps(st)) < 2000 else {"raw": json.dumps(st)[:2000]}
    hv = {}
    for m in re.finditer(r'\\?"(\w*(?:[vV]iew|[vV]isit|[zZ]obraz|[iI]mpression)\w*)\\?":\s*(\d+)', html):
        hv.setdefault(m.group(1), int(m.group(2)))
    if hv:
        out["htmlStats"] = dict(list(hv.items())[:20])
    m = re.search(r'\\"point\\":\{\\"latitude\\":\\"([\d.]+)\\",\\"longitude\\":\\"([\d.]+)\\"', html)
    if m:
        out["gps"] = [float(m.group(1)), float(m.group(2))]
    return out


def _fold(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _area_from_title(title):
    t = _fold(title).replace("\xa0", " ")
    if re.search(r"\d\s*(?:-|–|az|do)\s*\d+\s*(?:m2|m²)", t):
        return None
    m = re.search(r"(\d[\d .]{1,6})\s*(?:m2|m²|m\b|metrov)", t)
    if m:
        v = _num(m.group(1).replace(" ", "").replace(".", ""))
        if v and 150 <= v <= 20000:
            return v
    m = re.search(r"(\d+(?:[,.]\d+)?)\s*ar\b", t)
    if m:
        v = _num(m.group(1))
        if v and 1.5 <= v <= 200:
            return round(v * 100)
    return None


UTIL = {
    "voda": r"vodovod|obecn\w* vod|verejn\w* vod|\bvoda\b|\bvody\b|vodu\b|vodomer|studn",
    "elektrina": r"elektrin|elektrick|elektro|rozvadzac|\bnn\b|istenim",
    "kanalizacia": r"kanaliz",
    "plyn": r"\bplyn",
    "optika": r"optik|optick",
}
ON_PLOT = r"na pozemk|na hranic|privedeny|privedena|privedene|pripojk|vodomern|rozvadzac na|zrealizovan|pripraven\w* elektr|uz su|je zavedena|zavedene"
NEAR = r"v dosahu|pri pozemk|pred pozemk|v ulici|v blizkosti|moznost\w* napojeni|na hranici|pri pristupovej|v obci|v lokalite"


def _window(t, a, b, w=90):
    return t[max(0, a - w): b + w]


def extract(title, desc):
    raw = f"{title or ''}. {desc or ''}"
    t = _fold(raw)
    r = {}

    # rozmery
    dims = []
    for m in re.finditer(r"(\d{1,3}(?:[,.]\d{1,2})?)\s*m?\s*[x×]\s*(\d{1,3}(?:[,.]\d{1,2})?)\s*m\b", t):
        a, b = _num(m.group(1)), _num(m.group(2))
        if a and b and 5 <= a <= 200 and 5 <= b <= 200 and 150 <= a * b <= 20000:
            ctx = t[max(0, m.start() - 40): m.start()]
            if re.search(r"dom|zastavan|stavb|garaz|terasa|bazen", ctx) and not re.search(r"pozem", ctx):
                continue
            dims.append((min(a, b), max(a, b)))
    if not dims:
        w = re.search(r"sirk\w*[^.\d]{0,25}?(\d{1,3}(?:[,.]\d)?)\s*m", t)
        l = re.search(r"(?:dlzk|hlbk)\w*[^.\d]{0,25}?(\d{1,3}(?:[,.]\d)?)\s*m", t)
        if w and l:
            a, b = _num(w.group(1)), _num(l.group(1))
            if a and b and 5 <= a <= 200 and 5 <= b <= 200:
                dims.append((min(a, b), max(a, b)))
    if dims:
        r["width"], r["length"] = dims[0]
        if len(dims) > 1 and dims[1] != dims[0]:
            r["dimsNote"] = "; ".join(f"{a:g}×{b:g} m" for a, b in dims[:3])

    # tvar
    if re.search(r"nepravideln|lichobezn|klinov|trojuhol", t):
        r["shape"] = "nepravidelný"
    elif re.search(r"stvorcov|takmer stvorc", t):
        r["shape"] = "štvorcový"
    elif re.search(r"pravideln\w* tvar|obdlznik", t):
        r["shape"] = "pravidelný"
    if re.search(r"uzk\w* (?:a dlh|pas|pozem)|dlh\w* a uzk", t):
        r["shape"] = "úzky pás"

    # terén
    if re.search(r"rovinat|rovny pozemok|rovinny|v rovine", t):
        r["terrain"] = "rovina"
    if re.search(r"mierne svah|mierny svah|miernom svahu|mierne sklon|jemn\w* svah|mierne sklonen", t):
        r["terrain"] = "mierny svah"
    elif re.search(r"svahovit|\bsvah\b|vo svahu|prudk", t) and "terrain" not in r:
        r["terrain"] = "svah"

    # siete
    util, detail = {}, {}
    for k, rx in UTIL.items():
        for m in re.finditer(rx, t):
            ctx = _window(t, m.start(), m.end(), 70)
            neg = re.search(r"\bbez\b[^.]{0,25}" + rx.split("|")[0][:6], ctx) or re.search(r"(nie je|nieje|chyba)[^.]{0,30}(" + rx + ")", ctx)
            if k == "kanalizacia" and (neg or re.search(r"zump|septik|cov\b|cistiare", t) and not re.search(r"kanaliz\w*[^.]{0,40}(na pozemk|v dosahu|privedena|pripojk|v ulici)", t)):
                util[k] = False
                detail[k] = "žumpa / bez kanalizácie"
                break
            if neg:
                util[k] = False
                detail[k] = "nie je"
                break
            util[k] = True
            if re.search(ON_PLOT, ctx):
                detail[k] = "na pozemku"
            elif re.search(NEAR, ctx):
                detail.setdefault(k, "v dosahu")
            else:
                detail.setdefault(k, "spomenutá")
            if detail.get(k) == "na pozemku":
                break
    if re.search(r"zump|septik", t) and "kanalizacia" not in util:
        util["kanalizacia"] = False
        detail["kanalizacia"] = "žumpa"
    if re.search(r"inzinierske siete[^.]{0,30}(na pozemk|privedene)|vsetky (inzinierske )?siete|kompletn\w* (inzinierske )?siete", t):
        for k in ("voda", "elektrina"):
            util.setdefault(k, True)
            detail.setdefault(k, "na pozemku")
    if util:
        r["utilities"] = util
        r["utilDetail"] = detail

    # parcela (najprv výslovné „parcelné číslo“, potom ostatné zmienky)
    m = re.search(r"parceln\w* cisl\w*\s*[:.]?\s*(?:c-kn|kn-c|reg\.\s*c|kn c)?\s*[:.]?\s*(\d{1,5}/\d{1,4})", t) or re.search(r"(?:parc\w*\.?\s*(?:c\.|cislo)?|c-kn|kn-c|kn c|reg\.\s*c)\s*[:.]?\s*(?:c-kn|kn-c|reg\.\s*c)?\s*[:.]?\s*(?:c\.\s*)?(\d{1,5}/\d{1,4})", t)
    if m:
        r["parcel"] = m.group(1)
    m = re.search(r"k\.\s*u\.\s*([a-z][a-z \-]{2,30}?)(?:[,.;]|\s+(?:okres|parc|o vymere|s vymerou|v|na)\b)", t)
    if m:
        r["kuText"] = m.group(1).strip()

    # druh pozemku a územný plán
    if re.search(r"orn\w* pod|trval\w* travn|\bttp\b|lesn\w* pozem|polnohospodar", t):
        r["landType"] = "poľnohosp. pôda"
    elif re.search(r"zastavan\w* ploch\w* a nadvor", t):
        r["landType"] = "zastavaná plocha"
    elif re.search(r"\bzahrad[ay]\b[^.]{0,20}(druh|evidovan)|druh[^.]{0,20}zahrad", t):
        r["landType"] = "záhrada"
    if re.search(r"nie je (zahrnut|v uzemnom|sucast)|mimo uzemn\w* plan|zmena uzemn\w* plan|v procese zmeny|stavebn\w* uzaver|nie je stavebn", t):
        r["upOk"] = False
    elif re.search(r"(v|do|podla) uzemn\w* plan\w*[^.]{0,40}(ibv|rodinn|byvan|vystavb)|(schvalen|zahrnut)\w*[^.]{0,30}uzemn|urcen\w* na (vystavbu|ibv)|ibv", t):
        r["upOk"] = True

    # povolenia a projekt
    if re.search(r"stavebn\w* povolen", t) and not re.search(r"bez stavebn\w* povolen", t):
        r["permit"] = True
    if re.search(r"uzemn\w* rozhodnut", t):
        r["zoning"] = True
    if re.search(r"projekt\w* (rd|rodin|domu|na dom)|s projektom|\+ ?projekt|pozemok\+projekt", t):
        r["project"] = True

    # prístup a okolie
    if re.search(r"asfalt", t):
        r["access"] = "asfaltová cesta"
    elif re.search(r"spevnen\w* (pristup|cest)", t) and not re.search(r"nespevnen", t):
        r["access"] = "spevnená cesta"
    elif re.search(r"nespevnen|polna cest|poln\w* cest", t):
        r["access"] = "nespevnená cesta"
    if re.search(r"slep\w* ulic|slepa|nepriechodn|koniec ulice|na konci ulice", t):
        r["mainRoad"] = False
        r["street"] = "slepá ulica"
    elif re.search(r"(mimo|bez) (hlavn|rusn)|tich\w* (cast|ulic|lokal)|pokojn\w* (cast|ulic|lokal)|klud", t):
        r["mainRoad"] = False
        r["street"] = "tichá časť"
    elif re.search(r"(pri|pri hlavnej|na hlavnej|popri) (hlavnej )?(ceste|ceste i)|hlavn\w* cest\w* (pred|pri)", t):
        r["mainRoad"] = True
        r["street"] = "pri hlavnej ceste"
    if re.search(r"zaplav", t):
        r["flood"] = "spomína záplavy" if not re.search(r"mimo zaplav|nie je v zaplav|bez zaplav", t) else "mimo záplavovej oblasti"

    # typ ponuky
    if re.search(r"rekreacn|chat[auy]\b|chatov|zahradk", _fold(title or "")) or re.search(r"pre chatu|chatov\w* oblast|chatov\w* lokal|rekreacn\w* pozem|na rekreaci", t):
        r["category"] = "rekreacny"
    if r.get("landType") == "poľnohosp. pôda" and r.get("upOk") is not True:
        r["category"] = "nestavebny"
    if re.search(r"rezervovan", _fold(title or "")) or re.search(r"\b(je )?rezervovan", t[:300]):
        r["reserved"] = True
    if re.search(r"predan[ey]\b", _fold(title or "")):
        r["sold"] = True
    if re.search(r"dva (stavebne )?pozemky|2 pozemky|viacero pozemkov|pozemky? (o|s) vymer\w* \d+ (a|aj) \d+|\d+ ?m2? a \d+ ?m2", t):
        r["multi"] = True
    if re.search(r"investicn", _fold(title or "")):
        r["investment"] = True
    # druh ponuky podľa textu (stavebný / investičný / rekreačný / poľnohospodársky)
    ft = _fold(title or "")
    KINDS = [("investičný", r"investicn\w* (pozem|ucel|zamer|vystavb|projekt)|na investiciu|pre investor"),
             ("poľnohospodársky", r"orn\w* pod|trval\w* travn|\bttp\b|polnohospodar"),
             ("stavebný", r"stavebn\w* pozem|pozem\w* (na|pre) (vystavbu|rodinn|rd|ibv)|\bibv\b|na vystavbu rodinn|stavebn\w* parcel"),
             ("rekreačný", r"rekreacn|chatov|\bchat[auy]\b|zahradk")]
    in_title = [k for k, rx in KINDS if re.search(rx, ft)]
    in_text = [k for k, rx in KINDS if re.search(rx, t)]
    if in_title or in_text:
        r["kind"] = (in_title or in_text)[0]
        both = [k for k in dict.fromkeys(in_title + in_text)]
        if len(both) > 1:
            r["kindNote"] = "v texte: " + ", ".join(both)
    r["titleArea"] = _area_from_title(title or "")
    return r


def merge_area(page, ex):
    """Výmera: štruktúrovaná hodnota portálu, ale ak nesedí s názvom, platí názov (portál ju občas plní zle)."""
    ld, ta = page.get("ldArea"), ex.get("titleArea")
    if ta and (not ld or ld < 150 or abs(ld - ta) > 5):
        return ta
    return ld
