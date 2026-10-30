"""Build data.json from a folder of plot JSON files and a settings JSON.
Usage: python3 tools/build_data.py <plots_dir> <settings.json> [notes_dir]
From notes only rating, ratingAt and seenAt are published; note text and status never."""
import json, sys, os, datetime
plots_dir, settings_path = sys.argv[1], sys.argv[2]
notes_dir = sys.argv[3] if len(sys.argv) > 3 else None
KEEP_SETTINGS = ["directions","villages","areaMin","areaMax","priceMax","terrain","maxRatio","showReserved","origin"]
KEEP_PLOT = ["village","title","direction","minutes","minutesOrigin","originKey","lat","lng","precise","parcel","cadastralArea","area","price","width","length","terrain","utilities","mainRoad","category","reserved","summary","links","photoUrl","imageUrl","firstSeen","lastSeen","priceHistory","gone","goneReason","source","check","utilDetail","shape","access","street","permit","project","zoning","landType","upOk","dimsNote","agent","published","multi","flood","invalid","kind","kindNote","firstPublished"]
s = json.load(open(settings_path))
s = s.get("data", s)
plots = []
for f in sorted(os.listdir(plots_dir)):
    if not f.endswith(".json"): continue
    d = json.load(open(os.path.join(plots_dir, f)))
    d = d.get("data", d) if "data" in d and isinstance(d.get("data"), dict) else d
    p = {k: d[k] for k in KEEP_PLOT if k in d}
    p["id"] = f[:-5]
    if notes_dir and os.path.exists(os.path.join(notes_dir, f)):
        n = json.load(open(os.path.join(notes_dir, f)))
        n = n.get("data", n) if isinstance(n.get("data"), dict) else n
        for k in ("rating", "ratingAt", "seenAt"):
            if n.get(k): p[k] = n[k]
    plots.append(p)
out = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(), "settings": {k: s[k] for k in KEEP_SETTINGS if k in s}, "plots": plots}
json.dump(out, open("data.json", "w"), ensure_ascii=False, indent=1)
print(len(plots), "plots")
