/* Browser preview of the Android app. All menu and profile data comes from the same public sources as src/data.ts. */
const localize=window.WULunchI18n||{language:'de',locale:'de-AT',apply(){},refresh:async()=>{}};
const menuUrl='https://phoenixvie.github.io/wu-lunch/data/menus.json';
const supabase='https://vswnqdqnohbuzbwmsdvv.supabase.co';
const publishableKey='sb_publishable__LAhcQOUGtE-ACAN-RPKkw_UB7Nrub2';
const contactUrl=location.hostname==='localhost'||location.hostname==='127.0.0.1'?'./restaurant-contact.json':'https://phoenixvie.github.io/wu-lunch/data/restaurant-contact.json';
const publishedContactUrl='https://phoenixvie.github.io/wu-lunch/data/restaurant-contact.json';
const types={mensa:'International',campus:'International',baschly:'Orientalisch',finn:'International',karmafood:'International',losteria:'Italienisch',gruenehuette:'Österreichisch',glashaus:'Österreichisch',lia:'Café',topfdeckel:'Österreichisch',omakueche:'International'};
const locations={mensa:[16.4098281,48.2129611],campus:[16.41021,48.21213],baschly:[16.40743,48.21445],glashaus:[16.4120651,48.2118847],losteria:[16.4052,48.21468],gruenehuette:[16.40406,48.21758],lia:[16.4082722,48.2138325],topfdeckel:[16.4156227,48.2128709],omakueche:[16.4155067,48.2130071],karmafood:[16.4078761,48.218283]};
const addresses={mensa:'Welthandelsplatz 1, D1/TC, 1020 Wien',campus:'Welthandelsplatz 1, Gebäude D2, 1020 Wien',baschly:'Welthandelsplatz 1, Gebäude D4, 1020 Wien',glashaus:'Am Grünen Prater 11, 1020 Wien',losteria:'Freudplatz 2, 1020 Wien',omakueche:'Vorgartenstraße 206B/1, 1020 Wien',topfdeckel:'Vorgartenstraße 206B, 1020 Wien',gruenehuette:'Prater 196, 1020 Wien',lia:'Welthandelsplatz 1, LC, 1020 Wien',karmafood:'Ausstellungsstraße 63, 1020 Wien',finn:'Welthandelsplatz 1, Gebäude EA, 1020 Wien'};
const app=document.getElementById('app');
const nativePost=(type,values={})=>{if(!window.ReactNativeWebView)return false;window.ReactNativeWebView.postMessage(JSON.stringify({type,...values}));return true};
let mapAssetsLoading=false;
let data=null,selectedId=new URLSearchParams(location.search).get('restaurant'),selectedMapId=null,homeTab='list',detailTab='menu',dayIndex=0,map=null,lastPayload='',sourceViewUrl=null;
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const safeUrl=value=>{try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:''}catch{return ''}};
const icon=(name,extra='')=>`<span class="material-symbols-outlined ${extra}" aria-hidden="true">${esc(name)}</span>`;
const dateValue=(date,opts)=>new Intl.DateTimeFormat(localize.locale,{timeZone:'UTC',...opts}).format(new Date(date+'T12:00:00Z'));
const googleMapsUrl=r=>'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(r.name+' '+(r.address||addresses[r.id]||'Wien'));
const dates=()=>Array.from({length:5},(_,i)=>{const d=new Date(data.weekStart+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+i);return d.toISOString().slice(0,10)});
const currentRestaurant=()=>data?.restaurants.find(r=>r.id===selectedId);
const adjacentRestaurantId=step=>{const restaurants=data?.restaurants||[];if(!restaurants.length)return null;const index=restaurants.findIndex(r=>r.id===selectedId);return restaurants[(index+step+restaurants.length)%restaurants.length].id};
function logo(r){if(r.logoUrl)return `<img class="logo" src="${esc(r.logoUrl)}" alt="${esc(r.name)}">`;const letter=(r.name.replace(/^WU\s+/i,'').trim()[0]||'?').toLocaleUpperCase('de-AT');return `<span class="logo logo-fallback logo-${esc(r.id)}" style="${r.brandColor?'background:'+esc(r.brandColor):''}" aria-label="${esc(r.name)}">${esc(letter)}</span>`}
function initialDayIndex(){const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Vienna',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());return Math.max(0,dates().indexOf(today))}
function iconButton(name,label,action){return `<button type="button" data-action="${action}" aria-label="${esc(label)}">${icon(name)}<span>${esc(label)}</span></button>`}
function price(d){if(d.category==='Ausgabe 5'&&d.price==null)return '';if(d.priceLabel)return d.priceLabel;if(d.price_small!=null||d.price_large!=null)return [d.price_small,d.price_large].map(v=>v==null?'–':price({price:v})).join(' / ');return d.price==null?'X €':new Intl.NumberFormat(localize.locale,{maximumFractionDigits:2}).format(d.price)+' €'}
function dishRank(d){const c=(d.category||'').toLowerCase(),n=(d.name||'').toLowerCase();return /suppe|soup/.test(c)||(/suppe/.test(n)&&!c.includes('hauptgericht'))?0:/salat|salad/.test(c)?2:/nachspeise|dessert|süßspeise/.test(c)?3:1}
function restaurantDisplayRules(id,raw){
  const rows=raw.map(item=>({...item,allergens:[],name:item.name.replace(/\s*\([ABCDEFGHLMNOPR](?:\s*[,/]\s*[ABCDEFGHLMNOPR])*\)/g,'')}));
  if(id==='campus')return rows.map(item=>({...item,description:'Suppe oder Salat · Dessert',included_choices:[],menu_options:[]}));
  if(id==='lia')return rows.map(item=>({...item,name:item.name.replace(/\s+(?:und|mit)\s+grünem\s+Salat\s*$/i,''),description:'',included_choices:[],menu_options:[]}));
  if(id==='finn')return rows.filter(item=>! /suppe|salat|soup|salad|dessert/i.test(item.category||'')).map(item=>{
    const combo=(item.menu_options||[]).find(option=>/suppe/i.test(option.label||'')&&Number.isFinite(option.total_price));
    const salad=/\s+(?:und|mit)\s+grünem\s+Salat\s*$/i.test(item.name);
    return {...item,name:item.name.replace(/\s+(?:und|mit)\s+grünem\s+Salat\s*$/i,''),price:id==='finn'?(combo?combo.total_price:null):item.price,description:'Mit Tagessuppe'+(salad?' und grünem Salat':''),included_choices:[],menu_options:[]};
  });
  if(id==='karmafood')return rows.map(item=>({...item,description:'',included_choices:[],menu_options:[]}));
  if(id==='omakueche')return rows.map(item=>({...item,name:item.name.replace(/\s*\(Erwachsene\)/gi,''),description:'',included_choices:[],menu_options:[]}));
  if(id==='gruenehuette')return rows.map(item=>/suppe|soup/i.test(item.category||'')?
    {...item,name:item.name.replace(/^Suppen zur Auswahl:\s*/i,'').replace(/\boder,\s*/gi,'oder '),description:'Optional zum Tagesteller',detailInline:true}:
    {...item,description:'',included_choices:[]});
  if(id!=='topfdeckel')return rows;
  const light=rows.find(item=>/light lunch/i.test(item.name)),big=rows.find(item=>/big lunch/i.test(item.name));
  return rows.filter(item=>! /salat|salad|dessert|nachspeise/i.test(item.category||'') && ! /haussalat|dessert des tages/i.test(item.name) && !(light&&big&&item===big)).map(item=>{
    if(item===light||item===big)return {...item,name:'Hauptgericht (klein/groß) + kleine Suppe/Salat, Getränk oder Dessert',description:'',
      price_small:light?.price??null,price_large:big?.price??null,menu_options:[]};
    if(/suppe|soup/i.test(item.category||'')||/suppe/i.test(item.name))return {...item,description:'',price:null,priceLabel:' ',menu_options:[]};
    return {...item,description:'(klein / groß)',included_choices:[],menu_options:[]};
  });
}

function mensaStations(raw){
  if(!raw.length)return [];
  const seen=new Set();
  raw=raw.map(item=>({...item,allergens:[],name:item.name.replace(/\s*\([ABCDEFGHLMNOPR](?:\s*[,/]\s*[ABCDEFGHLMNOPR])*\)/g,'')})).filter(item=>{
    const key=JSON.stringify([item.category,item.name.toLowerCase().replace(/[^a-z0-9äöü]+/g,' ').trim(),item.price]);
    if(seen.has(key))return false;seen.add(key);return true;
  });
  const planted=raw.find(item=>/mensa burger/i.test(item.name)&&/planted.*crispy.*chicken/i.test(item.name)&&! /\bbeef\b/i.test(item.name));
  const beef=raw.find(item=>/mensa burger/i.test(item.name)&&/\bbeef\b/i.test(item.name));
  if(planted&&beef&&planted.category===beef.category&&planted.price===beef.price){
    if(!/planted/i.test(beef.name))beef.name=beef.name.replace(/\bBeef\b/i,"Beef oder "+planted.name.slice(planted.name.toLowerCase().indexOf('planted')));
    beef.description=[...new Set([beef.description,planted.description].filter(Boolean))].join('\n');
    raw=raw.filter(item=>item!==planted);
  }
  const normalize=s=>String(s||'').toLowerCase().replace(/[^a-z0-9äöü]+/g,' ').trim();
  const specs=[['Ausgabe 1+2',['powered by plants veggie','powered by plants','veggie','ausgabe 1 2']],['Ausgabe 3+4',['meaty','ausgabe 3 4']],['Ausgabe 5',['pizza','pizza co','weekly special','ausgabe 5']],['Ausgabe 6',['pasta','pasta co','ausgabe 6']],['Ausgabe 7',['bowls','bowls co','ausgabe 7']],['Ausgabe 8',['global grill','global grills','ausgabe 8']]];
  const assigned=new Set(),out=[];
  const soup=raw.find(item=>/^(tagess?uppe)$/i.test(item.category||''));
  const euro=v=>new Intl.NumberFormat('de-AT',{maximumFractionDigits:2}).format(v)+' €';
  for(const [label,categories] of specs){
    const rows=raw.filter(item=>categories.includes(normalize(item.category)));
    rows.forEach(item=>assigned.add(item));
    if(label==='Ausgabe 5'){out.push({category:label,name:'Pizza',price:null,description:''});continue}
    if(label==='Ausgabe 6'||label==='Ausgabe 7'){out.push({category:label,name:label==='Ausgabe 6'?'Pasta':'Bowl',price:null,priceLabel:' ',description:''});continue}
    if(!rows.length)continue;
    const prices=[...new Set(rows.map(item=>item.price))];
    const common=prices.length===1?prices[0]:null;
    const lines=rows.map(item=>[item.name+(prices.length>1?' – '+(item.price==null?'X €':euro(item.price)):''),item.description,item.energy_kcal?item.energy_kcal+' kcal':''].filter(Boolean).join('\n'));
    out.push({category:label,name:((label==='Ausgabe 1+2'||label==='Ausgabe 3+4')&&soup?soup.name+'\n':'')+lines.join('\n\n'),price:common,priceLabel:prices.length>1?' ':undefined,description:''});
  }
  // Soup and conditional menu offers retain their original terms and prices.
  return [...out.filter(item=>!['Ausgabe 5','Ausgabe 6','Ausgabe 7'].includes(item.category)),...raw.filter(item=>!assigned.has(item)&&! /tagess?uppe|soup deal|menüoption|smart menü/i.test(item.category||item.name))];
}

function dishes(r,date){let raw=r.days?.[date]||[];if(!r.manualDays?.[date]){if(raw.length&&r.validFrom&&r.validUntil&&(date<r.validFrom||date>r.validUntil))raw=[];if(!raw.length&&r.status==='seasonal')raw=r.seasonal||[]}
  if(raw.length&&raw.every(d=>d.manual_presentation))return raw;if(r.id==='mensa')return mensaStations(raw);raw=restaurantDisplayRules(r.id,raw);
  const result=[];for(const d of [...raw].sort((a,b)=>dishRank(a)-dishRank(b))){if(r.id==='topfdeckel'&&/gratis-dessert zum start|dein erstes dessert geht auf uns/i.test(d.name))continue;const detail=d.description||((d.included_choices||[]).length?'Mit '+d.included_choices.join(' oder '):'');result.push({...d,description:detail});for(const opt of d.menu_options||[])if(opt&&Number.isFinite(opt.total_price))result.push({name:'Optional: '+opt.label,price:opt.total_price})}return result}
function renderList(){return `<div class="group">WU Food</div><div class="scroll" id="list-scroll">${data.restaurants.map(r=>`<button type="button" class="restaurant-row" data-restaurant="${esc(r.id)}">${logo(r)}<span class="restaurant-copy"><span class="restaurant-name">${esc(r.name)}</span><span class="restaurant-type" style="display:block">${esc(r.restaurantType||types[r.id]||'Restaurant')}</span></span>${icon('chevron_right','chevron')}</button>`).join('')}<footer class="list-footer"><a href="https://phoenixvie.github.io/wu-lunch/impressum.html">Impressum</a><a href="https://phoenixvie.github.io/wu-lunch/">Webseite</a></footer></div>`}
function mealPresentation(d){
  const detail=d.description||'';
  if(detail==='Suppe oder Salat · Dessert')return {starter:'Suppe oder Salat',detail:'',dessert:'Dessert'};
  const included=/^Mit\s+((?:Tages)?suppe|(?:klein(?:em|er)?\s+|grün(?:em|er)?\s+)?Salat)(?:\s+(oder|und)\s+((?:Tages)?suppe|(?:klein(?:em|er)?\s+|grün(?:em|er)?\s+)?Salat))?\.?$/i.test(detail.trim());
  return !d.detailInline&&Number.isFinite(d.price)&&(included||detail==='Suppe oder Salat · Dessert')?{starter:detail.trim().replace(/^Mit\s+/i,'').replace(/\.$/,''),detail:''}:{starter:'',detail};
}
const linkLabel=url=>String(url).replace(/^https?:\/\//i,'').replace(/\/+$/,'');
function renderMenu(r){const ds=dates(),date=ds[dayIndex],menu=dishes(r,date),source=safeUrl(r.menuSourceUrl||r.url);return `<section class="menu-screen" id="menu-screen" style="--price-width:${Math.max(64,...menu.map(d=>price(d).length*7))}px"><div class="scroll menu-scroll" id="menu-scroll"><div class="weekday-strip" aria-label="Menütage">${ds.map((x,i)=>`<button type="button" class="weekday ${i===dayIndex?'active':''}" data-day="${i}" aria-label="${esc(dateValue(x,{weekday:'long',day:'2-digit',month:'2-digit'}))}" ${i===dayIndex?'aria-current="date"':''}><span>${esc(dateValue(x,{weekday:'long'}))}</span><span class="weekday-date">${esc(dateValue(x,{day:'2-digit',month:'2-digit'}))}</span></button>`).join('')}</div><div class="day-dots" aria-label="Wischanzeige">${ds.map((x,i)=>`<button type="button" class="day-dot ${i===dayIndex?'active':''}" data-day="${i}" aria-label="${esc(dateValue(x,{weekday:'long',day:'2-digit',month:'2-digit'}))}" ${i===dayIndex?'aria-current="date"':''}></button>`).join('')}</div>${menu.length?menu.map(d=>{const presentation=mealPresentation(d);return `<article class="dish"><div class="dish-heading"><span class="dish-name ${r.id==='mensa'&&/^Ausgabe\b/.test(d.category||'')?'mensa-station':''}">${r.id!=='mensa'&&(d.included_starter||d.included_soup)?`<span class="dish-starter">${esc(d.included_starter||d.included_soup)}</span>`:presentation.starter?`<span class="dish-starter">${esc(presentation.starter)}</span>`:''}${esc(r.id==='mensa'&&d.category?d.category:d.name)}${d.detailInline&&d.description?` <span style="font-weight:400">${esc(d.description)}</span>`:''}</span><span class="dish-price">${esc(price(d))}</span></div>${r.id==='mensa'&&d.category?`<div class="dish-description">${esc((d.included_starter||d.included_soup?(d.included_starter||d.included_soup)+'\n':'')+d.name)}</div>`:''}${presentation.detail&&!d.detailInline?`<div class="dish-description">${esc(presentation.detail)}</div>`:''}${d.included_dessert||presentation.dessert?`<div class="dish-description">${esc(d.included_dessert||presentation.dessert)}</div>`:''}${d.energy_kcal?`<div class="dish-allergens">${esc(d.energy_kcal)} kcal</div>`:''}</article>`}).join(''):'<p class="empty">Noch nicht veröffentlicht</p>'}</div><div class="source-note">Angaben ohne Gewähr. Bitte auf der ${source?'<button type="button" class="source-link" data-action="open-menu-source">Restaurantwebseite</button>':'Restaurantwebseite'} prüfen.</div></section>`}
function renderInfo(r){
  const address=r.address||addresses[r.id]||'';
  const menuWebsite=safeUrl(r.menuSourceUrl||r.url);
  const website=safeUrl(r.homepageUrl)||(menuWebsite?new URL(menuWebsite).origin+'/':'');
  const row=(label,value,url,symbol)=>`<div class="info-row">${icon(symbol,'info-icon')}<div class="info-value"><span class="info-label">${esc(label)}</span>${url?`<a href="${esc(url)}" target="${url.startsWith('http')?'_blank':'_self'}" rel="noopener noreferrer">${esc(/^https?:/i.test(url)?linkLabel(value):value)}</a>`:`<span class="info-missing">${esc(value||'Nicht hinterlegt')}</span>`}</div></div>`;
  return `<div class="scroll info-screen"><section class="info-hero" aria-label="Restaurant">${logo(r)}<div><h2>${esc(r.name)}</h2><p>${esc(r.restaurantType||types[r.id]||'Restaurant')}</p></div></section><section class="info-card" aria-label="Kontaktdaten">${row('Telefon',r.phone,r.phone?'tel:'+r.phone.replace(/[^+\d]/g,''):'','call')}${row('E-Mail',r.email,r.email?'mailto:'+r.email:'','mail')}${row('Webseite',website,website,'language')}${row('Webseite – Mittagsmenü',menuWebsite,menuWebsite,'restaurant_menu')}${row('Adresse',address,address?googleMapsUrl({...r,address}):'','location_on')}<div class="info-row">${icon('schedule','info-icon')}<div class="info-value"><span class="info-label">Öffnungszeiten</span>${r.hours?.length?`<ul class="info-hours-list">${r.hours.map(hour=>`<li>${esc(hour)}</li>`).join('')}</ul>`:'<span class="info-missing">Noch nicht hinterlegt</span>'}</div></div></section><section class="info-location"><h2>Standort</h2><div class="map info-map" id="map" aria-label="Standort von ${esc(r.name)}"></div></section></div>`;
}

function render(){if(!data)return;const r=currentRestaurant();if(map){map.remove();map=null}if(sourceViewUrl){app.innerHTML=`<div class="source-browser"><iframe title="Webseite von ${esc(r?.name||'Restaurant')}" src="${esc(sourceViewUrl)}" referrerpolicy="no-referrer" sandbox="allow-scripts allow-forms allow-same-origin allow-popups"></iframe></div><nav class="source-nav"><button data-action="close-source">Zurück</button></nav>`;localize.apply(app);return}app.innerHTML=r?`<header class="top detail"><button class="back" data-action="back" aria-label="Zurück zur Liste">${icon('arrow_back')}</button><h1>${esc(detailTab==='info'?'Restaurant':r.name)}</h1></header><div class="body">${detailTab==='menu'?renderMenu(r):renderInfo(r)}</div><nav class="tabs" aria-label="Restaurantansichten">${[['menu','restaurant_menu','Menü'],['info','info','Restaurant']].map(([id,symbol,label])=>`<button type="button" class="${detailTab===id?'active':''}" data-detail="${id}" ${detailTab===id?'aria-current="page"':''}>${icon(symbol)}${label}</button>`).join('')}<button type="button" data-action="previous-restaurant">${icon('arrow_back')}Zurück</button><button type="button" data-action="next-restaurant">${icon('arrow_forward')}Weiter</button></nav>`:`<header class="top"><div class="segment"><button type="button" data-home="list" class="${homeTab==='list'?'active':''}" ${homeTab==='list'?'aria-pressed="true"':''}>Liste</button><button type="button" data-home="map" class="${homeTab==='map'?'active':''}" ${homeTab==='map'?'aria-pressed="true"':''}>Karte</button></div></header><div class="body">${homeTab==='list'?renderList():'<div class="map" id="map"></div>'}</div>`;
  localize.apply(app);
  if((r&&detailTab==='info')||(!r&&homeTab==='map'))renderMap(r)}
function updateMapSelection(){document.querySelector('.map-selected')?.remove();if(!selectedMapId||selectedId)return;const r=data.restaurants.find(item=>item.id===selectedMapId);if(!r)return;document.getElementById('map')?.insertAdjacentHTML('beforeend',`<button type="button" class="map-selected restaurant-row" data-map-restaurant="${esc(r.id)}">${logo(r)}<span class="restaurant-copy"><span class="restaurant-name">${esc(r.name)}</span><span class="restaurant-type">${esc(r.restaurantType||types[r.id]||'Restaurant')}</span></span>${icon('chevron_right','chevron')}</button>`)}
function renderMap(focused){const element=document.getElementById('map');if(!window.maplibregl){if(!mapAssetsLoading&&document.head&&document.createElement){mapAssetsLoading=true;const css=document.createElement('link');css.rel='stylesheet';css.href='https://unpkg.com/maplibre-gl@5.11.0/dist/maplibre-gl.css';document.head.appendChild(css);const script=document.createElement('script');script.src='https://unpkg.com/maplibre-gl@5.11.0/dist/maplibre-gl.js';script.async=true;document.head.appendChild(script)}element.innerHTML='<p class="map-message">Karte wird geladen …</p>';setTimeout(()=>{if(document.getElementById('map')===element)renderMap(focused)},500);return}const center=focused?(focused.longitude!=null&&focused.latitude!=null?[focused.longitude,focused.latitude]:locations[focused.id]):[16.409,48.2133];map=new maplibregl.Map({container:element,style:'https://tiles.openfreemap.org/styles/liberty',center:center||[16.409,48.2133],zoom:focused?16:14.5,attributionControl:false});map.on('click',()=>{if(!focused&&selectedMapId){selectedMapId=null;updateMapSelection()}});for(const r of focused?[focused]:data.restaurants){const coords=r.longitude!=null&&r.latitude!=null?[r.longitude,r.latitude]:locations[r.id];if(!coords)continue;const marker=document.createElement('span');marker.className='map-letter-pin';marker.textContent=(r.name.replace(/^WU\s+/i,'')[0]||'?').toUpperCase();marker.style.background=r.brandColor||({mensa:'#e30613',finn:'#49654e',baschly:'#8a55a6',campus:'#387dda',lia:'#4a579b',karmafood:'#c65b40',topfdeckel:'#6cb78e',gruenehuette:'#448b54',glashaus:'#9c2426',losteria:'#e44750',omakueche:'#c9a581'}[r.id]||'#087cf4');marker.setAttribute('aria-label',r.name);marker.addEventListener('click',event=>{event.stopPropagation();if(!focused){selectedMapId=r.id;updateMapSelection()}});new maplibregl.Marker({element:marker,anchor:'bottom'}).setLngLat(coords).addTo(map)}if(focused)element.insertAdjacentHTML('beforeend',`<a class="map-external" href="${esc(googleMapsUrl(focused))}" target="_blank" rel="noopener noreferrer">${icon('open_in_new')}In Google Maps öffnen</a>`);element.insertAdjacentHTML('beforeend','<div class="map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> · <a href="https://openfreemap.org/" target="_blank" rel="noopener noreferrer">OpenFreeMap</a></div>');updateMapSelection()}
app.addEventListener('click',async e=>{
  const link=e.target.closest('a[href]');if(link){const url=safeUrl(link.href);if(url){e.preventDefault();if(!nativePost('open-source',{url,title:currentRestaurant()?.name||'Restaurant'})){sourceViewUrl=url;render()}return}if(window.ReactNativeWebView){e.preventDefault();nativePost('open-external',{url:link.href});return}}
  const target=e.target.closest('[data-action],[data-restaurant],[data-map-restaurant],[data-home],[data-detail],[data-day]');
  if(!target)return;
  if(target.dataset.restaurant||target.dataset.mapRestaurant){selectedId=target.dataset.restaurant||target.dataset.mapRestaurant;selectedMapId=null;sourceViewUrl=null;dayIndex=initialDayIndex();detailTab='menu';render();return}
  if(target.dataset.home){if(homeTab==='map'&&target.dataset.home==='map'){selectedMapId=null;updateMapSelection();return}homeTab=target.dataset.home;selectedMapId=null;render();return}
  if(target.dataset.detail){detailTab=target.dataset.detail;render();return}
  if(target.dataset.day!==undefined){dayIndex=Number(target.dataset.day);render();return}
  switch(target.dataset.action){
    case'back':selectedId=null;selectedMapId=null;sourceViewUrl=null;render();break;
    case'open-menu-source':{const r=currentRestaurant(),url=safeUrl(r?.menuSourceUrl||r?.url);if(!url)break;if(!nativePost('open-source',{url,title:r.name})){sourceViewUrl=url;render()}break}
    case'close-source':sourceViewUrl=null;render();break;
    case'previous-restaurant':
    case'next-restaurant':selectedId=adjacentRestaurantId(target.dataset.action==='next-restaurant'?1:-1);sourceViewUrl=null;render();break;
    case'share':{const message='Gehen wir heute '+currentRestaurant()?.name+' zu Mittag?';if(nativePost('share',{text:message}))break;if(navigator.share)try{await navigator.share({text:message})}catch{}else navigator.clipboard?.writeText(message);break}
    case'retry':load();break;
  }
});
let swipeStart=null;
app.addEventListener('touchstart',e=>{
  swipeStart=e.target.closest('#menu-screen')&&e.touches.length===1?{x:e.changedTouches[0].screenX,y:e.changedTouches[0].screenY}:null;
},{passive:true});
app.addEventListener('touchend',e=>{
  if(!swipeStart)return;
  const deltaX=e.changedTouches[0].screenX-swipeStart.x,deltaY=e.changedTouches[0].screenY-swipeStart.y;
  swipeStart=null;
  if(Math.abs(deltaX)>60&&Math.abs(deltaX)>Math.abs(deltaY)*1.2){
    e.preventDefault();
    dayIndex=Math.max(0,Math.min(4,dayIndex+(deltaX<0?1:-1)));render();
  }
},{passive:false});
app.addEventListener('touchcancel',()=>{swipeStart=null},{passive:true});
async function rows(path){const response=await fetch(supabase+'/rest/v1/'+path,{cache:'no-store',headers:{apikey:publishableKey}});if(!response.ok)throw new Error('Live-Änderungen konnten nicht geladen werden');return response.json()}
function applyPayload(incoming,profiles,manual,contact){const oldWeek=data?.weekStart;const byId=new Map(profiles.map(p=>[p.restaurant_id,p]));incoming.restaurants=incoming.restaurants.filter(r=>byId.get(r.id)?.is_enabled!==false).map(r=>{const p=byId.get(r.id),info=contact[r.id]||{};r={...r,days:{...r.days},manualDays:{},menuSourceUrl:p?.menu_url??r.url,homepageUrl:(safeUrl(p?.website_url)?new URL(p.website_url).origin+'/':'')||(r.id==='baschly'?'https://baschly.com/':(safeUrl(r.url)?new URL(r.url).origin+'/':'')),phone:info.phone,email:info.email,hours:p?.opening_hours??info.hours,hoursSource:info.source};if(p){r.name=p.display_name||r.name;r.restaurantType=p.restaurant_type||undefined;r.logoUrl=p.logo_url||undefined;r.phone=p.phone??r.phone;r.email=p.email??r.email;r.brandColor=p.brand_color;r.url=p.website_url||r.url;r.address=p.address||undefined;r.latitude=p.latitude??undefined;r.longitude=p.longitude??undefined}for(const m of manual)if(m.restaurant_id===r.id){r.days[m.menu_date]=Array.isArray(m.dishes)?m.dishes:[];r.manualDays[m.menu_date]=true}return r}).sort((a,b)=>(byId.get(a.id)?.sort_order??9999)-(byId.get(b.id)?.sort_order??9999));data=incoming;if(selectedId&&!currentRestaurant()){selectedId=null;sourceViewUrl=null;detailTab='menu'}if(selectedMapId&&!data.restaurants.some(r=>r.id===selectedMapId))selectedMapId=null;if(oldWeek!==data.weekStart)dayIndex=initialDayIndex();render()}
let loadingMenus=false;
async function load(){void localize.refresh();if(loadingMenus)return;loadingMenus=true;try{const [response,profiles,localContactResponse]=await Promise.all([fetch(menuUrl+'?t='+Date.now(),{cache:'no-store'}),rows('restaurant_overrides?select=*'),fetch(contactUrl+'?t='+Date.now(),{cache:'no-store'})]);if(!response.ok)throw new Error('Menüs konnten nicht geladen werden');const incoming=await response.json();if(!incoming.weekStart||!Array.isArray(incoming.restaurants))throw new Error('Menüdaten sind ungültig');const manual=await rows('menu_day_overrides?week_start=eq.'+incoming.weekStart+'&select=restaurant_id,menu_date,dishes');const contactResponse=localContactResponse.ok?localContactResponse:await fetch(publishedContactUrl+'?t='+Date.now(),{cache:'no-store'});const contact=contactResponse.ok?(await contactResponse.json()).restaurants||{}:{};const payload=JSON.stringify([incoming,profiles,manual,contact]);if(payload===lastPayload)return;lastPayload=payload;applyPayload(incoming,profiles,manual,contact);try{localStorage.setItem('wu-food-live-v1',payload)}catch{}}catch(error){if(!data)app.innerHTML=`<div class="loading"><div class="spinner"></div><div class="error">${esc(error.message||'Laden fehlgeschlagen')}<br><button class="retry" data-action="retry">Erneut versuchen</button></div></div>`;console.error(error)}finally{loadingMenus=false}}
window.wuFoodBack=()=>{if(sourceViewUrl){sourceViewUrl=null;render()}else if(selectedId){selectedId=null;selectedMapId=null;render()}else if(homeTab==='map'){homeTab='list';selectedMapId=null;render()}else nativePost('exit')};
try{const cached=JSON.parse(localStorage.getItem('wu-food-live-v1')||'null');if(Array.isArray(cached)&&cached.length===4&&cached[0]?.weekStart&&Array.isArray(cached[0].restaurants))applyPayload(...cached)}catch{}
window.wuFoodRefresh=load;load();setInterval(load,3000);window.addEventListener?.('focus',()=>load());document.addEventListener('visibilitychange',()=>{if(!document.hidden)load()});
