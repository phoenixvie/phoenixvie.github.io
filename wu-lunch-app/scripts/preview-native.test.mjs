import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

test('packaged preview boots, wraps restaurants and sends menu sources to native browser', async () => {
  const generated = await readFile(new URL('../src/previewHtml.ts', import.meta.url), 'utf8');
  const html = JSON.parse(generated.match(/export const previewHtml = (.+);/)[1]);
  assert.ok(html.includes('data:font/'));
  assert.ok(!html.includes('href="./style.css"'));
  const code = html.match(/<script>(window.WU_FOOD_BUILD[\s\S]*?)<\/script>/)[1];
  const events = new Map(), actions = new Map(), messages = [], requests = [];
  let refresh,refreshMs;
  let profiles=[{restaurant_id:'mensa',website_url:'https://www.wumensa.at/'}], manual=[];
  const cache=new Map();
  const localStorage={getItem:key=>cache.get(key)||null,setItem:(key,value)=>cache.set(key,value)};
  const app = {innerHTML: '', addEventListener: (type, callback) => { const previous = actions.get(type); actions.set(type, previous ? event => { callback(event); previous(event); } : callback); }};
  const mapElement={innerHTML:''};
  const restaurants = [{id:'mensa',name:'WU Mensa',url:'https://www.wumensa.at/menuplan-deutsch/',days:{}},{id:'finn',name:'Finn',url:'https://finn.wien/blogs/news/mittagsmenu',days:{}}];
  class FixtureDate extends Date {constructor(...args){super(...(args.length?args:['2026-11-10T12:00:00Z']));}}
  const context = {URL, URLSearchParams, Intl, Date:FixtureDate, console, localStorage, navigator:{language:'de-AT'}, location:{hostname:'phoenixvie.github.io',search:''},
    document:{getElementById:id=>id==='map'?mapElement:app,addEventListener:(type,callback)=>events.set(type,callback)},
    setInterval:(callback,ms)=>{if(ms===3000){refresh=callback;refreshMs=ms;}return 0}, setTimeout:()=>0,
    ReactNativeWebView:{postMessage:value=>messages.push(JSON.parse(value))},
    fetch:async (url,options)=>{requests.push({url,options});return {ok:true,json:async()=>url.includes('lunch_ui_texts')?[]:url.includes('restaurant_overrides')?profiles:url.includes('menu_day_overrides')?manual:url.includes('restaurant-contact')?{restaurants:{mensa:{phone:'+43 123',email:'mensa@example.test',hours:['Mo–Fr 11:00–14:00']}}}:{weekStart:'2026-11-09',restaurants:JSON.parse(JSON.stringify(restaurants))}}}};
  context.window=context;
  vm.runInNewContext(code,context);
  assert.ok(events.has('DOMContentLoaded'));
  events.get('DOMContentLoaded')();
  for(let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve));
  assert.match(app.innerHTML,/WU Food/);
  for(const request of requests.filter(r=>r.url.includes('/rest/v1/'))){
    assert.equal(request.options.cache,'no-store');
    assert.ok([...new URL(request.url).searchParams.keys()].every(key=>['select','week_start','order','limit','offset','updated_at'].includes(key)),'PostgREST accepts only supported query parameters');
  }
  assert.equal(messages.filter(item=>item.type==='usage').length,0,'initial data load does not count restaurant usage');
  await refresh();assert.equal(messages.filter(item=>item.type==='usage').length,0,'polling does not count restaurant usage');
  const click=dataset=>actions.get('click')({target:{closest:selector=>selector==='a[href]'?null:{dataset}}});
  await click({restaurant:'mensa'});
  assert.match(app.innerHTML,/previous-restaurant/);
  assert.equal(messages.filter(item=>item.type==='usage').at(-1).event,'restaurant_open');
  assert.equal(messages.filter(item=>item.type==='usage').at(-1).props.restaurant_id,'mensa');
  await click({action:'open-menu-source'});
  assert.deepEqual(messages.at(-1),{type:'open-source',url:'https://www.wumensa.at/menuplan-deutsch/',title:'WU Mensa'});
  assert.ok(!app.innerHTML.includes('<iframe'));
  await click({day:'3'});
  await click({action:'previous-restaurant'});
  assert.match(app.innerHTML,/weekday active" data-day="3"/);
  assert.match(app.innerHTML,/<h1>Finn<\/h1>/);
  await click({action:'next-restaurant'});
  assert.match(app.innerHTML,/<h1>WU Mensa<\/h1>/);
  assert.match(app.innerHTML,/weekday active" data-day="3"/);
  await click({action:'share'});
  assert.equal(messages.at(-1).text,'Gehen wir heute zu WU Mensa Mittag essen? https://phoenixvie.github.io/wu-lunch-app/preview/?restaurant=mensa');
  await click({detail:'info'});
  assert.match(app.innerHTML,/<h1>Restaurant<\/h1>/);
  assert.match(app.innerHTML,/data-detail="info"[^>]*><span[^>]*>info<\/span>Restaurant/);
  assert.doesNotMatch(app.innerHTML,/Quelle: Restaurantwebseite|info-card info-hours/);
  assert.match(app.innerHTML,/info-row[^]*Öffnungszeiten[^]*info-hours-list/);
  assert.match(app.innerHTML,/info-hero/);assert.match(app.innerHTML,/WU Mensa/);
  assert.match(app.innerHTML,/tel:\+43123/);assert.match(app.innerHTML,/mailto:mensa@example.test/);
  assert.match(app.innerHTML,/Welthandelsplatz 1, D1\/TC, 1020 Wien/);
  assert.match(app.innerHTML,/Öffnungszeiten/);assert.match(app.innerHTML,/Mo–Fr 11:00–14:00/);
  assert.match(app.innerHTML,/info-map/);assert.match(mapElement.innerHTML,/Karte wird geladen/);
  assert.doesNotMatch(app.innerHTML,/Mit Freunden essen gehen|Kontaktiere das App Team|data-detail="contact"|data-detail="map"/);
  assert.match(app.innerHTML,/Webseite<\/span><a href="https:\/\/www.wumensa.at\/"/);
  assert.match(app.innerHTML,/>www\.wumensa\.at<\/a>/);
  assert.match(app.innerHTML,/>www\.wumensa\.at\/menuplan-deutsch<\/a>/);
  assert.match(app.innerHTML,/Webseite – Mittagsmenü<\/span><a href="https:\/\/www.wumensa.at\/menuplan-deutsch\/"/);
  await click({action:'next-restaurant'});
  assert.match(app.innerHTML,/<h1>Restaurant<\/h1>/);assert.match(app.innerHTML,/<h2>Finn<\/h2>/);
  await click({action:'next-restaurant'});
  assert.match(app.innerHTML,/<h2>WU Mensa<\/h2>/);
  await click({action:'previous-restaurant'});
  assert.match(app.innerHTML,/<h2>Finn<\/h2>/);
  await click({detail:'menu'});
  await click({action:'next-restaurant'});
  assert.match(app.innerHTML,/<h1>WU Mensa<\/h1>/);
  assert.match(app.innerHTML,/weekday active" data-day="3"/);
  assert.doesNotMatch(app.innerHTML,/day-heading/);
  assert.match(app.innerHTML,/Montag<\/span><span class="weekday-date">09\.11\.<\/span>/);
  const link={href:'https://www.google.com/maps/search/?api=1&query=WU'};
  actions.get('click')({preventDefault(){},target:{closest:selector=>selector==='a[href]'?link:null}});
  assert.deepEqual(messages.at(-1),{type:'open-source',url:link.href,title:'WU Mensa'});
  for (const href of ['tel:+4367688488254','mailto:office@wumensa.at']) {
    actions.get('click')({preventDefault(){},target:{closest:selector=>selector==='a[href]'?{href}:null}});
    assert.deepEqual(messages.at(-1),{type:'open-external',url:href});
  }
  assert.equal(refreshMs,3000);
  restaurants[0].days=Object.fromEntries(Array.from({length:5},(_,i)=>['2026-11-'+String(9+i).padStart(2,'0'),[{name:'Live aktualisiertes Gericht',category:'Meaty',price:6.4}]]));
  await refresh();
  assert.match(app.innerHTML,/Live aktualisiertes Gericht/);
  manual=[{restaurant_id:'mensa',menu_date:'2026-11-12',dishes:[{name:'Manuell korrigiertes Menü',price:8}]}];
  await refresh();assert.match(app.innerHTML,/Manuell korrigiertes Menü/);
  profiles=[{restaurant_id:'mensa',is_enabled:false},{restaurant_id:'finn',sort_order:0}];
  await refresh();assert.doesNotMatch(app.innerHTML,/WU Mensa/);assert.match(app.innerHTML,/Finn/);
  profiles=[{restaurant_id:'mensa',sort_order:2},{restaurant_id:'finn',sort_order:1}];
  await refresh();assert.ok(app.innerHTML.indexOf('data-restaurant="finn"')<app.innerHTML.indexOf('data-restaurant="mensa"'));
  assert.ok(cache.has('wu-food-live-v1'));
  const cachedApp={innerHTML:'',addEventListener(){}};
  const cachedContext={...context,document:{getElementById:()=>cachedApp,addEventListener:(name,fn)=>{if(name==='DOMContentLoaded')events.set('cached-ready',fn)}},fetch:()=>new Promise(()=>{})};
  cachedContext.window=cachedContext;
  vm.runInNewContext(code,cachedContext); // cached restaurant list renders before any network response
  events.get('cached-ready')();
  assert.match(cachedApp.innerHTML,/Finn/);assert.match(cachedApp.innerHTML,/WU Mensa/);

});

test('installed app carries its own meeting-point photo and every icon it shows', async () => {
  const read = path => readFile(new URL(path, import.meta.url), 'utf8');
  const [generated, app, meet] = await Promise.all([read('../src/previewHtml.ts'), read('../preview/app.js'), read('../preview/meet-live.js')]);
  const html = JSON.parse(generated.match(/export const previewHtml = (.+);/)[1]);
  // Foto: fest eingebaut (sonst zeigt die App je nach Stand der Webseite ein anderes Bild); die Web-Vorschau lädt die Datei.
  assert.match(html, /class="meet-photo-visible" src="data:image\/webp;base64,[A-Za-z0-9+/=]{1000,}"/);
  assert.doesNotMatch(html, /src="\.\/meeting-point\.webp"/);
  assert.match(meet, /src="\.\/meeting-point\.webp"/);
  // Symbole: Die App enthält nur eine kleine Auswahl der Symbolschrift (assets/material-symbols-font.json).
  // Jedes andere Symbol muss als Zeichnung in meetIcons stehen – sonst erscheint sein Name als Text ("CLOSE").
  const inFont = ['access_time','arrow_back','arrow_forward','call','chevron_right','email','info','language','launch','local_dining','local_phone','location_on','mail','map','open_in_new','phone','place','restaurant_menu','schedule'];
  const inline = Object.keys(JSON.parse(app.match(/const meetIcons=(\{.*?\});\n/s)[1]));
  const used = new Set([...(app + meet).matchAll(/\b(?:icon|fact)\('([a-z_]+)'/g)].map(match => match[1]));
  assert.ok(used.has('close') && used.size >= 10);
  for (const name of used) assert.ok(inline.includes(name) || inFont.includes(name), 'Symbol fehlt in der App: ' + name);
});

test('iOS screenshots can open a view by launch argument; anything else is ignored', async () => {
  const read = path => readFile(new URL(path, import.meta.url), 'utf8');
  const [native, app, meet] = await Promise.all([read('../App.tsx'), read('../preview/app.js'), read('../preview/meet-live.js')]);
  // Nur iOS, nur bekannte Werte; der Wert landet geprüft im Kopf der eingebetteten Seite.
  assert.match(native, /Platform\.OS === 'ios' \? String\(Settings\.get\('wuStartScreen'\)/);
  const pattern = new RegExp(native.match(/return \/(\^\(map\|meet[^/]+)\/\.test\(value\)/)[1]);
  for (const ok of ['map', 'meet', 'restaurant:mensa', 'info:lia']) assert.ok(pattern.test(ok), ok);
  for (const bad of ["map';alert(1)//", 'restaurant:', 'info:<b>', 'list ']) assert.ok(!pattern.test(bad), bad);
  assert.match(native, /window\.WU_START_SCREEN='\$\{startScreen\}'/);
  assert.match(app, /String\(window\.WU_START_SCREEN\|\|''\)\.split\(':'\)/);
  assert.match(meet, /window\.WU_START_SCREEN === 'meet'/);
});

test('UX follow-ups in the restaurant screens: readable small print, decorative dots and logos, diet badges, share, map fit, readable umlaut hosts', async () => {
  const read = path => readFile(new URL(path, import.meta.url), 'utf8');
  const [app, css] = await Promise.all([read('../preview/app.js'), read('../preview/style.css')]);
  // Kleinschrift mindestens 12,5 px in dunklerem Grau; Fußzeile 13 px.
  assert.match(css, /\.source-note\{color:#6b6b6b;font-size:12\.5px/);
  assert.match(css, /\.list-footer a\{[^}]*color:#5f6a75;font-size:13px/);
  assert.match(app, /size>10\.5\)\{size-=0\.25/);
  // Wischpunkte sind reine Anzeige (keine 7-px-Tippziele, keine doppelten Fokus-Stopps); Logos dekorativ.
  assert.match(app, /<div class="day-dots" aria-hidden="true">\$\{ds\.map\(\(x,i\)=>`<span class="day-dot/);
  assert.doesNotMatch(app, /class="day-dot[^"]*" data-day/);
  assert.match(app, /alt="" aria-hidden="true">`;/);
  assert.match(app, /aria-hidden="true">\$\{esc\(letter\)\}<\/span>`\}/);
  // Vegetarisch/vegan aus dem Import am Gericht.
  const context = {};
  vm.createContext(context);
  vm.runInContext(app.slice(app.indexOf('const dietBadge='), app.indexOf('\n', app.indexOf('const dietBadge='))).replace('const dietBadge=', 'var dietBadge='), context);
  assert.equal(context.dietBadge({diet: 'veggie'}), '<span class="dish-diet">vegetarisch</span>');
  assert.equal(context.dietBadge({diet: 'vegan'}), '<span class="dish-diet">vegan</span>');
  assert.equal(context.dietBadge({diet: 'meat'}), ''); assert.equal(context.dietBadge({}), '');
  assert.match(app, /\$\{dietBadge\(d\)\}<\/span><span class="dish-price">/);
  // Umlaut-Adressen lesbar; gewöhnliche Adressen unverändert.
  const linkContext = {};
  vm.createContext(linkContext);
  const start = app.indexOf('function punyDecode('), end = app.indexOf('\n', app.indexOf('const linkLabel='));
  vm.runInContext(app.slice(start, end).replace('const readableHost=', 'var readableHost=').replace('const linkLabel=', 'var linkLabel='), linkContext);
  assert.equal(linkContext.linkLabel('https://www.xn--omakche-q2a.at/'), 'www.omaküche.at');
  assert.equal(linkContext.linkLabel('https://www.xn--mnchen-3ya.de/speisekarte/'), 'www.münchen.de/speisekarte');
  assert.equal(linkContext.linkLabel('https://www.wumensa.at/menuplan-deutsch/'), 'www.wumensa.at/menuplan-deutsch');
  // Pins: zwei Buchstaben nur bei gleichem Anfangsbuchstaben.
  const pins = {};
  vm.createContext(pins);
  vm.runInContext(app.slice(app.indexOf('function pinLabels('), app.indexOf('\n', app.indexOf('function pinLabels('))), pins);
  const label = pins.pinLabels([{name: 'WU Mensa'}, {name: 'Das Campus'}, {name: 'Das Glashaus'}, {name: 'Finn'}]);
  assert.deepEqual([{name: 'WU Mensa'}, {name: 'Das Campus'}, {name: 'Das Glashaus'}, {name: 'Finn'}].map(label), ['M', 'DC', 'DG', 'F']);
  // Karte: alle Pins einpassen, Zoom-Knöpfe, Ladetext weg; Teilen-Knopf im Kopf mit Link zur App.
  assert.match(app, /map\.fitBounds\(bounds,\{padding:/);
  assert.match(app, /new maplibregl\.NavigationControl\(\{showCompass:false/);
  assert.match(app, /element\.innerHTML='';map=new maplibregl\.Map/);
  assert.match(app, /<button type="button" class="share" data-action="share" aria-label="Teilen">/);
  assert.match(app, /preview\/\?restaurant='\+encodeURIComponent\(selectedId\)/);
  // Menü-Link nur, wenn er sich von der Webseite unterscheidet.
  assert.match(app, /menuWebsite&&menuWebsite\.replace\(\/\\\/\+\$\/,''\)!==website\.replace/);
});
