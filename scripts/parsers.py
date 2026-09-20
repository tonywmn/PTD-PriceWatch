import json,re
from dataclasses import dataclass
from html import unescape

@dataclass
class Result:
    price: float|None
    availability: str
    validated: bool
    status: str

def norm(x):
    return re.sub(r'\s+',' ',unescape(x or '').replace('\u00ad','').replace('\xa0',' ')).strip()

def money(x):
    m=re.search(r'\d[\d.\s]*(?:,\d{2})?',norm(str(x)))
    if not m:return None
    s=m.group().replace(' ','')
    try:v=float(s.replace('.','').replace(',','.')) if ',' in s else float(s)
    except:return None
    return v if 300<=v<=3000 else None

def identity(provider,text):
    t=norm(text).lower()
    product=any(re.search(p,t) for p in [r'playstation\s*[®™]?\s*5\s*[-–]?\s*pro',r'ps5\s*[-–]?\s*pro',r'playstation\s*pro'])
    if provider in ('Geizhals DE','Idealo DE'): return product
    capacity=any(re.search(p,t) for p in [r'\b2\s*tb\b',r'\b2\.000\s*gb\b',r'\b2000\s*gb\b'])
    return product and capacity

NEG=[
 'dieser artikel ist dauerhaft ausverkauft','artikel ist dauerhaft ausverkauft',
 'unser aktionsangebot ist leider ausverkauft','derzeit nicht vorrätig',
 'zurzeit nicht verfügbar','artikel kann derzeit nicht gekauft werden',
 'aktuell ausverkauft','nicht auf lager','leider keine lieferung möglich','keine angebote']

def jsonld(html):
    out=[]
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html or '',re.I|re.S):
        try:stack=[json.loads(unescape(raw))]
        except:continue
        while stack:
            z=stack.pop()
            if isinstance(z,dict):
                name=norm(str(z.get('name','')))
                if identity('Geizhals DE',name):
                    offers=z.get('offers',{});offers=offers if isinstance(offers,list) else [offers]
                    for o in offers:
                        if isinstance(o,dict):out.append((money(o.get('price') or o.get('lowPrice')),str(o.get('availability','')).lower()))
                stack.extend(z.values())
            elif isinstance(z,list):stack.extend(z)
    return out

def price_for(provider,text,html):
    t=norm(text)
    patterns={
      'PlayStation Direct DE':[r'PlayStation\s*[®™]?\s*5\s*Pro(?:\s*Konsole)?\s*[-–]?\s*2\s*TB[\s\S]{0,500}?(\d{3,4},\d{2})\s*€',r'(\d{3,4},\d{2})\s*€[\s\S]{0,350}?(?:Lagerung|Speicher)\s*:\s*2\s*TB'],
      'Alternate DE':[r'PlayStation\s*5\s*Pro\s*2\s*TB[\s\S]{0,800}?€\s*(\d{3,4},\d{2})',r'€\s*(\d{3,4},\d{2})'],
      'Geizhals DE':[r'\bab\s*€?\s*(\d{1,4}(?:\.\d{3})*,\d{2})',r'Aktueller Preisbereich[\s\S]{0,100}?€\s*(\d{1,4}(?:\.\d{3})*,\d{2})'],
      'Idealo DE':[r'(?:Neu\s+)?ab\s+(\d{1,4}(?:\.\d{3})*,\d{2})\s*€',r'Bester Preis[\s\S]{0,100}?(\d{1,4}(?:\.\d{3})*,\d{2})\s*€'],
      'Amazon.de':[r'Playstation\s*5\s*Pro\s*2\s*TB[\s\S]{0,900}?(\d{3,4},\d{2})\s*€'],
      'Expert DE':[r'PlayStation[®™]?5\s*Pro[\s\S]{0,900}?(\d{3,4},\d{2})\s*€'],
      'MediaMarkt DE':[r'PlayStation[®™]?5\s*Pro[\s\S]{0,900}?(\d{3,4},\d{2})\s*€'],
      'Saturn DE':[r'PlayStation[®™]?5\s*Pro[\s\S]{0,900}?(\d{3,4},\d{2})\s*€']}
    for p in patterns.get(provider,[]):
        m=re.search(p,t,re.I)
        if m:
            v=money(m.group(1))
            if v:return v
    return next((v for v,_ in jsonld(html) if v is not None),None)

def parse_text(provider,text,html=''):
    combined=norm(text+' '+re.sub(r'<[^>]+>',' ',html or ''))
    if not identity(provider,combined):return Result(None,'unknown',False,'Produktidentität nicht bestätigt')
    low=norm(text).lower();neg=next((x for x in NEG if x in low),None)
    price=price_for(provider,text,html)
    if neg:return Result(price,'unavailable',False,f'Nicht verfügbar: {neg}')
    offers=jsonld(html)
    structured=any('instock' in a or 'limitedavailability' in a for _,a in offers)
    if provider in ('Geizhals DE','Idealo DE'):
        available=price is not None and ('angebote' in low or 'preisvergleich' in low or 'neu ab' in low)
    elif provider in ('MediaMarkt DE','Saturn DE'):
        available='in den warenkorb' in low and 'lieferung nach hause' in low
    elif provider=='Amazon.de':available='in den einkaufswagen' in low
    elif provider=='Alternate DE':available='in den warenkorb' in low
    elif provider=='PlayStation Direct DE':available='in den warenkorb' in low or 'jetzt kaufen' in low
    else:available=structured or 'in den warenkorb' in low or 'sofort lieferbar' in low
    if available and price is not None:return Result(price,'available',True,'Preis & Verfügbarkeit bestätigt')
    if price is not None:return Result(price,'unknown',False,'Preis erkannt, Verfügbarkeit unbestätigt')
    if available:return Result(None,'available',False,'Verfügbarkeit erkannt, Preis unbestätigt')
    return Result(None,'unknown',False,'Nicht eindeutig bestätigt')
