#!/usr/bin/env python3
"""FoodPlan: REWE product search proxy and local offer reader.
REWE's shop search endpoint is undocumented and may change; prices may depend on selected shop.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs, quote
from html.parser import HTMLParser
from urllib.error import URLError, HTTPError
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json, re, os

BASE = Path(__file__).resolve().parent
OFFERS_URL = "https://www.rewe.de/angebote/syke/540502/rewe-hauptstr-56-58-suurend/"
REWE_SUGGEST_URL = "https://shop.rewe.de/api/suggestions?q="
REWE_PRODUCTS_URL = "https://shop.rewe.de/api/products?search="
OFF_URL = "https://world.openfoodfacts.org/cgi/search.pl?search_terms={}&search_simple=1&action=process&json=1&page_size=8"

class TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"): self.skip += 1
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3", "article"): self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip: self.skip -= 1
        if tag in ("p", "div", "li", "h1", "h2", "h3", "article"): self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip:
            value=" ".join(data.split())
            if value: self.parts.append(value)

def get_url(url, accept="application/json"):
    req=Request(url, headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36 FoodPlan/1.1", "Accept":accept, "Accept-Language":"de-DE,de;q=0.9,en;q=0.7"})
    with urlopen(req, timeout=18) as resp: return resp.read().decode('utf-8','replace')

def extract_offers(html):
    parser=TextExtractor(); parser.feed(html)
    lines=[re.sub(r"\s+"," ",x).strip() for x in "\n".join(parser.parts).splitlines()]
    lines=[x for x in lines if x]; found=[]; seen=set()
    for i,line in enumerate(lines):
        m=re.search(r"(?<!\d)(\d{1,3}[,.]\d{2})\s*€",line)
        if not m: continue
        price=m.group(1).replace('.',',')+' €'; candidates=[]
        for candidate in lines[max(0,i-6):i]:
            c=re.sub(r"\s+"," ",candidate).strip()
            if 3 < len(c) < 90 and not re.search(r"€|kg\s*=|l\s*=|Knaller|Aktion|Bonus|je \d|versch\. Sorten|gültig|Angebote|Prospekt|REWE",c,re.I): candidates.append(c)
        name=candidates[-1] if candidates else "REWE-Angebot"; key=(name.lower(),price)
        if key in seen: continue
        seen.add(key); detail=lines[i+1] if i+1<len(lines) and len(lines[i+1])<100 and not re.search(r"€|Knaller|Aktion",lines[i+1],re.I) else ""
        found.append({"name":name,"price":price,"detail":detail})
        if len(found)>=40: break
    return found

def walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values(): yield from walk_dicts(v)
    elif isinstance(obj, list):
        for v in obj: yield from walk_dicts(v)

def first_value(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}): return d[k]
    return None

def numeric_price(value):
    if isinstance(value, dict):
        value=first_value(value, ("value","amount","price","gross","formatted","displayValue"))
    if isinstance(value, (int,float)) and 0 < float(value) < 10000: return float(value)
    if isinstance(value,str):
        m=re.search(r"(\d{1,4}[,.]\d{2})",value.replace("\u00a0"," "))
        if m:
            try: return float(m.group(1).replace(',','.'))
            except ValueError: pass
    return None

def parse_pack(text, d):
    raw=first_value(d,("grammage","quantity","unit","size","packageSize","netContent","volume"))
    s=str(raw or "") + " " + str(text or "")
    m=re.search(r"(?<!\d)(\d+(?:[,.]\d+)?)\s*(kg|g|ml|l)\b",s,re.I)
    if not m: return 1000 if re.search(r"\b1\s*l\b",s,re.I) else 1000
    n=float(m.group(1).replace(',','.')); unit=m.group(2).lower()
    return n*1000 if unit in ("kg","l") else n

def extract_products(payload):
    results=[]; seen=set()
    for d in walk_dicts(payload):
        name=first_value(d,("productName","name","title","displayName","label"))
        if not isinstance(name,str) or len(name.strip())<2: continue
        # Avoid category/navigation labels and non-product wrappers.
        if name.lower() in {"produkte","produkte anzeigen","suche","rewe","mehr anzeigen"}: continue
        price_value=first_value(d,("price","salesPrice","currentPrice","displayPrice","priceValue","offerPrice","grossPrice"))
        price=numeric_price(price_value)
        # Avoid accepting parent objects that only contain a brand/title and no SKU-like signal.
        sku=first_value(d,("productId","id","sku","articleNumber","ean","gtin"))
        if price is None and not sku: continue
        pack=parse_pack(name,d)
        brand=first_value(d,("brand","brandName"))
        if isinstance(brand,dict): brand=first_value(brand,("name","label"))
        image=first_value(d,("imageUrl","image","thumbnail","imageURL"))
        if isinstance(image,dict): image=first_value(image,("url","src"))
        url=first_value(d,("url","productUrl","canonicalUrl","href"))
        if isinstance(url,str) and url.startswith("/"): url="https://shop.rewe.de"+url
        key=(name.strip().lower(),price)
        if key in seen: continue
        seen.add(key)
        results.append({"id":str(sku or name),"name":name.strip(),"brand":str(brand or ""),"price":price,"pack":pack,"unit":"ml" if re.search(r"\b(ml|l)\b",name,re.I) else "g","image":image if isinstance(image,str) and image.startswith("https://") else "","url":url if isinstance(url,str) and url.startswith("http") else "","source":"REWE-Onlineshop","nutrition":None})
        if len(results)>=30: break
    return results

def extract_off_nutrition(query):
    try:
        raw=get_url(OFF_URL.format(quote(query)), "application/json")
        data=json.loads(raw)
        products=data.get("products",[])
        q=set(re.findall(r"[a-z0-9]+",query.lower()))
        best=None; best_score=0
        for p in products:
            title=(p.get("product_name_de") or p.get("product_name") or "").strip()
            if not title: continue
            words=set(re.findall(r"[a-z0-9]+",title.lower()))
            score=len(q & words)/max(1,len(q))
            n=p.get("nutriments",{})
            vals={"kcal":n.get("energy-kcal_100g"),"p":n.get("proteins_100g"),"f":n.get("fat_100g"),"c":n.get("carbohydrates_100g")}
            if all(v is not None for v in vals.values()) and score>best_score:
                best_score=score; best={**vals,"matched_name":title,"source":"Open Food Facts","match_score":round(score,2)}
        return best if best and best_score>=0.45 else None
    except Exception: return None

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(BASE),**kwargs)
    def end_headers(self):
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); super().end_headers()
    def do_GET(self):
        parsed=urlparse(self.path); path=parsed.path; qs=parse_qs(parsed.query)
        if path == '/health': return self._json(200,{'status':'ok'})
        if path == '/api/products':
            query=(qs.get('q') or [''])[0].strip()
            if len(query)<2: return self._json(400,{'error':'Bitte mindestens zwei Zeichen eingeben.','products':[]})
            try:
                errors=[]; products=[]
                try:
                    data=json.loads(get_url(REWE_SUGGEST_URL+quote(query), 'application/json'))
                    products=extract_products(data)
                except Exception as e: errors.append(str(e))
                if not products:
                    try:
                        data=json.loads(get_url(REWE_PRODUCTS_URL+quote(query)+'&page=1','application/json'))
                        products=extract_products(data)
                    except Exception as e: errors.append(str(e))
                if not products:
                    return self._json(502,{'products':[],'error':'REWE hat keine maschinenlesbaren Suchergebnisse geliefert. Die REWE-Suche kann sich ändern oder den Abruf blockieren.','source':'https://shop.rewe.de/','details':errors[:1]})
                return self._json(200,{'products':products,'updated_at':datetime.now(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y %H:%M'),'source':'https://shop.rewe.de/','note':'Preise werden vom REWE-Onlineshop geliefert und sind standortabhängig; wenn für Syke keine Onlinepreise vorliegen, können Preise fehlen.'})
            except Exception as e: return self._json(502,{'products':[],'error':f'REWE-Produktsuche fehlgeschlagen: {e}'})
        if path == '/api/nutrition':
            query=(qs.get('q') or [''])[0].strip()
            if len(query)<2: return self._json(400,{'nutrition':None,'error':'Suchbegriff zu kurz.'})
            return self._json(200,{'nutrition':extract_off_nutrition(query)})
        if path != '/api/offers':
            if path == '/': self.path='/index.html'
            return super().do_GET()
        try:
            html=get_url(OFFERS_URL,'text/html')
            offers=extract_offers(html)
            payload={'offers':offers,'updated_at':datetime.now(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y %H:%M'),'source':OFFERS_URL,'note':'Öffentlich sichtbare Angebotsdaten; keine vollständige Sortiments- oder Regalpreisliste.'}
            if not offers: payload['message']='Die REWE-Seite wurde erreicht, aber aktuelle Angebote konnten nicht zuverlässig ausgelesen werden. Bitte nutze den offiziellen REWE-Link.'
            self._json(200,payload)
        except (HTTPError,URLError,TimeoutError,OSError) as e: self._json(502,{'error':f'REWE konnte nicht abgerufen werden ({e}).','offers':[]})
    def _json(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False).encode('utf-8'); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,fmt,*args): print('[%s] %s'%(self.log_date_time_string(),fmt%args))

if __name__ == '__main__':
    port=int(os.environ.get('PORT','8000')); server=ThreadingHTTPServer(('0.0.0.0',port),Handler)
    print(f'FoodPlan läuft auf 0.0.0.0:{port}')
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nServer beendet.')
    finally: server.server_close()
