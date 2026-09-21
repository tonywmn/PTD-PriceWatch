/* Append after current app.js content. Requires global sb, sources, $, load and scannerActive. */
let ptdScanState='idle';
let ptdPreviousPrices=JSON.parse(localStorage.getItem('ptdPreviousPrices')||'{}');
let ptdVisitedAt=localStorage.getItem('ptdVisitedAt');

function ensureEnhancedUI(){
 if(!document.querySelector('#scanOverlay')){
  document.body.insertAdjacentHTML('beforeend',`<div id="scanOverlay" class="scan-overlay" aria-live="polite"><div class="scan-panel"><div class="scan-spinner"></div><h3>Angebote werden geprüft …</h3><p id="scanProgressText">Scan wird vorbereitet</p><div class="scan-progress"><span id="scanProgressBar"></span></div></div></div>`);
 }
 if(!document.querySelector('#summaryStrip')){
  const metrics=document.querySelector('.metric-grid');
  metrics?.insertAdjacentHTML('afterend','<section id="summaryStrip" class="summary-strip"></section>');
 }
}
function freshnessFor(source){
 const value=source.last_success_at||source.last_checked_at;
 if(!value||source.status?.toLowerCase().includes('blockiert'))return ['unknown','Nicht erfolgreich bestätigt'];
 const age=(Date.now()-new Date(value).getTime())/60000;
 if(age<=20)return ['fresh','Erfolgreich aktualisiert'];
 if(age<=180)return ['stale','Letzte erfolgreiche Aktualisierung älter'];
 return ['unknown','Daten veraltet'];
}
function enhanceCards(){
 const available=sources.filter(s=>s.availability==='available').length;
 const unavailable=sources.filter(s=>s.availability==='unavailable').length;
 const unknown=sources.length-available-unavailable;
 const strip=document.querySelector('#summaryStrip');
 if(strip)strip.innerHTML=`<div class="summary-item"><strong>${available}</strong><span>verfügbar</span></div><div class="summary-item"><strong>${unavailable}</strong><span>nicht verfügbar</span></div><div class="summary-item"><strong>${unknown}</strong><span>unbestätigt</span></div>`;
 document.querySelectorAll('.provider-card').forEach(card=>{
  const heading=card.querySelector('h3');const source=sources.find(s=>s.providers.name===heading?.textContent);if(!source)return;
  const [cls,label]=freshnessFor(source);const changed=source.last_price!=null&&ptdPreviousPrices[source.id]!=null&&Number(ptdPreviousPrices[source.id])!==Number(source.last_price);
  card.querySelector('.freshness')?.remove();card.insertAdjacentHTML('beforeend',`<div class="freshness ${cls}"><span class="freshness-dot"></span>${label}</div>`);
  if(changed){card.classList.add(Number(source.last_price)<Number(ptdPreviousPrices[source.id])?'price-down':'price-up');if(ptdVisitedAt&&new Date(source.last_checked_at)>new Date(ptdVisitedAt))heading.insertAdjacentHTML('beforeend','<span class="new-badge">NEU</span>')}
  if(source.last_price!=null)ptdPreviousPrices[source.id]=source.last_price;
 });
 localStorage.setItem('ptdPreviousPrices',JSON.stringify(ptdPreviousPrices));localStorage.setItem('ptdVisitedAt',new Date().toISOString());
}
function setStatusVisual(state){
 const dot=document.querySelector('.live-dot');const label=document.querySelector('#systemStatus');if(!dot||!label)return;
 dot.classList.remove('active','scanning','paused','failed');
 if(state==='running'){dot.classList.add('scanning');label.textContent='Scanner prüft Angebote';return}
 if(state==='failed'){dot.classList.add('failed');label.textContent='Letzter Scan fehlgeschlagen';return}
 const active=scannerActive();dot.classList.add(active?'active':'paused');label.textContent=active?'Scanner aktiv · werktags 07:00–17:00':'Scanner pausiert · aktiv werktags 07:00–17:00';
}
async function pollScanStatus(){
 const {data}=await sb.from('scan_status').select('*').eq('id',1).maybeSingle();if(!data)return;
 ptdScanState=data.state;setStatusVisual(data.state);const overlay=document.querySelector('#scanOverlay');const total=Math.max(data.total_sources||0,1),done=Math.min(data.completed_sources||0,total);const running=data.state==='running';overlay?.classList.toggle('visible',running);
 const text=document.querySelector('#scanProgressText');const bar=document.querySelector('#scanProgressBar');if(text)text.textContent=data.current_provider?`${done} von ${total} · ${data.current_provider}`:`${done} von ${total} Quellen geprüft`;if(bar)bar.style.width=`${Math.round(done/total*100)}%`;
 if(!running&&window.__ptdWasRunning){await load({silent:true});enhanceCards()}window.__ptdWasRunning=running;
}
function startEnhancements(){ensureEnhancedUI();enhanceCards();pollScanStatus();setInterval(pollScanStatus,5000);setInterval(()=>setStatusVisual(ptdScanState),60000)}
window.addEventListener('load',()=>setTimeout(startEnhancements,500));
