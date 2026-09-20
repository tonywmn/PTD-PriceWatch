import json,re
from dataclasses import dataclass
@dataclass
class Result:
 price:float|None; availability:str; validated:bool; status:str

def money(x):
 if x is None:return None
 s=re.sub(r'[^0-9,.]','',str(x))
 try:return float(s.replace('.','').replace(',','.')) if ',' in s else float(s)
 except:return None

def identity_ok(text):
 t=text.lower();return ('playstation' in t or 'ps5' in t) and 'pro' in t and any(x in t for x in ('2 tb','2tb','2.000 gb','2000 gb'))

def parse_jsonld(html):
 out=[]
 for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.I|re.S):
  try: stack=[json.loads(raw)]
  except:continue
  while stack:
   z=stack.pop()
   if isinstance(z,dict):
    n=str(z.get('name',''))
    if identity_ok(n):
     offers=z.get('offers',{});offers=offers if isinstance(offers,list) else [offers]
     for o in offers:
      if isinstance(o,dict):out.append((money(o.get('price') or o.get('lowPrice')),str(o.get('availability','')).lower()))
    stack.extend(z.values())
   elif isinstance(z,list):stack.extend(z)
 return out

def parse_text(provider,text,html=''):
 low=text.lower()
 if not identity_ok(text):return Result(None,'unknown',False,'Produktidentität nicht bestätigt')
 negative=['dauerhaft ausverkauft','aktionsangebot ist leider ausverkauft','leider keine lieferung möglich','derzeit nicht vorrätig','artikel kann derzeit nicht gekauft werden','aktuell ausverkauft','nicht auf lager','keine angebote']
 neg=next((x for x in negative if x in low),None)
 price=None; available=False
 if provider=='Geizhals DE':
  m=re.search(r'(?:neu\s+)?ab\s*(?:€\s*)?([0-9.]+,[0-9]{2})',text,re.I);price=money(m.group(1)) if m else None;available=bool(re.search(r'\b[1-9]\d*\s+Angebote?',text,re.I)) and not neg
 elif provider=='Idealo DE':
  m=re.search(r'Neu\s+ab\s+([0-9.]+,[0-9]{2})\s*€',text,re.I);price=money(m.group(1)) if m else None;available=price is not None and not neg
 elif provider=='Alternate DE':
  m=re.search(r'€\s*([0-9.]+,[0-9]{2})',text);price=money(m.group(1)) if m else None;available='in den warenkorb' in low and not neg
 else:
  js=parse_jsonld(html)
  if js:price=js[0][0];available=('instock'in js[0][1] or 'limitedavailability'in js[0][1]) and not neg
  if provider in ('MediaMarkt DE','Saturn DE'):available=('in den warenkorb'in low and 'lieferung nach hause'in low and not neg)
  if provider=='Amazon.de':available=('in den einkaufswagen'in low and not neg)
  if provider=='PlayStation Direct DE':available=(('in den warenkorb'in low or 'jetzt kaufen'in low) and not neg)
 if price is not None and not 500<=price<=2500:price=None
 validated=price is not None and available
 return Result(price,'available' if available else 'unavailable' if neg else 'unknown',validated,'Bestätigt' if validated else f'Nicht verfügbar: {neg}' if neg else 'Nicht eindeutig bestätigt')
