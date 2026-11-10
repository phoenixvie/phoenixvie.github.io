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
  const events = new Map(), actions = new Map(), messages = [];
  let refresh,refreshMs;
  const app = {innerHTML: '', addEventListener: (type, callback) => actions.set(type, callback)};
  const mapElement={innerHTML:''};
  const restaurants = [{id:'mensa',name:'WU Mensa',url:'https://www.wumensa.at/menuplan-deutsch/',days:{}},{id:'finn',name:'Finn',url:'https://finn.wien/blogs/news/mittagsmenu',days:{}}];
  const context = {URL, URLSearchParams, Intl, Date, console, navigator:{}, location:{hostname:'phoenixvie.github.io',search:''},
    document:{getElementById:id=>id==='map'?mapElement:app,addEventListener:(type,callback)=>events.set(type,callback)},
    setInterval:(callback,ms)=>{refresh=callback;refreshMs=ms;return 0}, setTimeout:()=>0,
    ReactNativeWebView:{postMessage:value=>messages.push(JSON.parse(value))},
    fetch:async url=>({ok:true,json:async()=>url.includes('restaurant_overrides')?[{restaurant_id:'mensa',website_url:'https://www.wumensa.at/'}]:url.includes('menu_day_overrides')?[]:url.includes('restaurant-contact')?{restaurants:{mensa:{phone:'+43 123',email:'mensa@example.test',hours:['Mo–Fr 11:00–14:00']}}}:{weekStart:'2026-11-09',restaurants:JSON.parse(JSON.stringify(restaurants))}})};
  context.window=context;
  vm.runInNewContext(code,context);
  assert.ok(events.has('DOMContentLoaded'));
  events.get('DOMContentLoaded')();
  for(let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve));
  assert.match(app.innerHTML,/WU Food/);
  const click=dataset=>actions.get('click')({target:{closest:selector=>selector==='a[href]'?null:{dataset}}});
  await click({restaurant:'mensa'});
  assert.match(app.innerHTML,/previous-restaurant/);
  await click({action:'open-menu-source'});
  assert.deepEqual(messages.at(-1),{type:'open-source',url:'https://www.wumensa.at/menuplan-deutsch/',title:'WU Mensa'});
  assert.ok(!app.innerHTML.includes('<iframe'));
  await click({action:'previous-restaurant'});
  assert.match(app.innerHTML,/<h1>Finn<\/h1>/);
  await click({action:'next-restaurant'});
  assert.match(app.innerHTML,/<h1>WU Mensa<\/h1>/);
  await click({action:'share'});
  assert.equal(messages.at(-1).text,'Gehen wir heute WU Mensa zu Mittag?');
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
  await click({detail:'menu'});
  assert.match(app.innerHTML,/<h2 class="day-heading">\d{1,2}\. November 2026<\/h2>/);
  const link={href:'https://www.google.com/maps/search/?api=1&query=WU'};
  actions.get('click')({preventDefault(){},target:{closest:selector=>selector==='a[href]'?link:null}});
  assert.deepEqual(messages.at(-1),{type:'open-source',url:link.href,title:'WU Mensa'});
  assert.equal(refreshMs,3000);
  restaurants[0].days=Object.fromEntries(Array.from({length:5},(_,i)=>['2026-11-'+String(9+i).padStart(2,'0'),[{name:'Live aktualisiertes Gericht',category:'Meaty',price:6.4}]]));
  await refresh();
  assert.match(app.innerHTML,/Live aktualisiertes Gericht/);
});
