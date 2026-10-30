import requests
UA={"User-Agent":"pozemky-mapa/1.0 (+https://github.com/LukasMaX1/pozemky-mapa_LM)"}
for u in ["https://kataster.skgeodesy.sk/eskn/rest/services?f=json",
          "https://kataster.skgeodesy.sk/eskn/rest/services/VRM/parcels_c_view/MapServer?f=json",
          "https://zbgis.skgeodesy.sk/mapka/sk/kataster",
          "https://inspirews.skgeodesy.sk/geoserver/cp/ows?service=WFS&request=GetCapabilities",
          "https://www.skgeodesy.sk/",
          "https://kataster.skgeodesy.sk/"]:
    try:
        r=requests.get(u,headers=UA,timeout=20); print("==",u,r.status_code,r.headers.get("access-control-allow-origin")); print(r.text[:2500])
    except Exception as e: print("==",u,"ERR",str(e)[:150])
