import requests, json
UA={"User-Agent":"pozemky-mapa/1.0 (+https://github.com/LukasMaX1/pozemky-mapa_LM)"}
B="https://inspirews.skgeodesy.sk/geoserver/cp/ows"
def g(params, n=1500):
    try:
        r=requests.get(B,params=params,headers=UA,timeout=60)
        print("==",r.status_code,r.headers.get("content-type"),r.url[:200]); print(r.text[:n])
    except Exception as e: print("ERR",e)
g({"service":"WFS","version":"2.0.0","request":"GetCapabilities"},3000)
g({"service":"WFS","version":"2.0.0","request":"DescribeFeatureType","typeNames":"cp:CP.CadastralParcel"},3000)
# Gyňov bbox ~ 48.62,21.33 ; small bbox
bb="48.620,21.330,48.630,21.345,urn:ogc:def:crs:EPSG::4326"
g({"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":"cp:CP.CadastralParcel","bbox":bb,"count":"3","outputFormat":"application/json"},3000)
g({"service":"WFS","version":"2.0.0","request":"GetFeature","typeNames":"cp:CP.CadastralParcel","bbox":bb,"count":"2"},3000)
g({"service":"WFS","version":"1.1.0","request":"GetFeature","typeName":"cp:CP.CadastralParcel","count":"2","maxFeatures":"2","CQL_FILTER":"areaValue BETWEEN 697 AND 699","outputFormat":"application/json"},2000)
# rerun
