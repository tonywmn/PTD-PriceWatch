import os,sys,random,time,json
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import requests
from playwright.sync_api import sync_playwright
from pywebpush import webpush,WebPushException
from parsers import parse_text
URL=os.environ['SUPABASE_URL'];KEY=os.environ['SUPABASE_SECRET_KEY'];H={'apikey':KEY,'Authorization':f'Bearer {KEY}','Content-Type':'application/json','Prefer':'return=representation'}
def api(path,method='GET',payload=None):
 r=requests.request(method,URL+'/rest/v1/'+path,headers=H,json=payload,timeout=30);r.raise_for_status();return r.json() if r.text else None
def upsert_alert(payload):
 r=requests.post(URL+'/rest/v1/alert_state?on_conflict=source_id',headers={**H,'Prefer':'resolution=merge-duplicates,return=minimal'},json=payload,timeout=30);r.raise_for_status()
def business_time():
 n=datetime.now(ZoneInfo('Europe/Berlin'));return n.weekday()<5 and 7<=n.hour<17
def due(s):
 if not s.get('next_check_at'):return True
 return datetime.fromisoformat(s['next_check_at'].replace('Z','+00:00'))<=datetime.now(ZoneInfo('UTC'))
def notify(product,source):
 subs=api('push_subscriptions?active=eq.true&select=*') or [];pub=os.getenv('VAPID_PUBLIC_KEY');priv=os.getenv('VAPID_PRIVATE_KEY');
 if not(pub and priv):return
 payload=json.dumps({'title':'PS5 Pro Preisalarm','body':f"{source['last_price']:.2f} € bei {source['providers']['name']} · verfügbar",'url':os.getenv('APP_URL','https://tonywmn.github.io/PTD-PriceWatch/'),'tag':f"price-{source['id']}"})
 for sub in subs:
  try:webpush({'endpoint':sub['endpoint'],'keys':{'p256dh':sub['p256dh'],'auth':sub['auth']}},payload,vapid_private_key=priv,vapid_claims={'sub':'mailto:pricewatch@example.com'})
  except WebPushException as e:
   if getattr(e.response,'status_code',0) in (404,410):api(f"push_subscriptions?endpoint=eq.{requests.utils.quote(sub['endpoint'],safe='')}",'PATCH',{'active':False})
def main():
if not business_time() and os.getenv('FORCE_SCAN', 'false').lower() != 'true':
 print('Outside configured business window')
 return
 products=api('products?active=eq.true&select=*') or []
 sources=api('product_sources?active=eq.true&select=*,providers(*)') or []
 products_by={x['id']:x for x in products};todo=[x for x in sources if due(x)]
 if not todo:print('No source due');return
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for s in todo:
   checked=datetime.now(ZoneInfo('UTC'));next_at=checked+timedelta(minutes=random.randint(5,10));patch={'last_checked_at':checked.isoformat(),'next_check_at':next_at.isoformat()}
   page=browser.new_page(locale='de-DE',viewport={'width':1440,'height':1000})
   try:
    page.goto(s['product_url'],wait_until='domcontentloaded',timeout=45000);page.wait_for_timeout(random.randint(1800,3500));text=page.locator('body').inner_text(timeout=15000);html=page.content();r=parse_text(s['providers']['name'],text,html);patch.update({'last_price':r.price,'availability':r.availability,'status':r.status,'error_message':None})
    if r.validated:patch['last_success_at']=checked.isoformat()
    api(f"product_sources?id=eq.{s['id']}",'PATCH',patch);api('price_history','POST',{'source_id':s['id'],'price':r.price,'availability':r.availability,'validated':r.validated,'checked_at':checked.isoformat()})
    product=products_by.get(s['product_id']);
    if product and r.validated and r.price<product['alert_price']:
     state=(api(f"alert_state?source_id=eq.{s['id']}&select=*")or[None])[0]
     if not state or state.get('last_alert_price')!=r.price or not state.get('alert_active'):
      notify(product,{**s,**patch});upsert_alert({'source_id':s['id'],'last_alert_price':r.price,'last_alert_at':checked.isoformat(),'alert_active':True})
    else:upsert_alert({'source_id':s['id'],'alert_active':False})
   except Exception as e:patch.update({'status':'Abruffehler','error_message':str(e)[:500]});api(f"product_sources?id=eq.{s['id']}",'PATCH',patch)
   finally:page.close();time.sleep(random.uniform(1.1,2.4))
  browser.close()
if __name__=='__main__':main()
